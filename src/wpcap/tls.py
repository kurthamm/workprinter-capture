"""A tiny local certificate authority so the page can be HTTPS on a home network."""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

# Apple devices refuse TLS server certificates valid for more than 825 days, even from a
# user-installed CA, so the server certificate is short-lived and renewed by `serve`.
SERVER_CERT_DAYS = 825
RENEW_WITHIN = dt.timedelta(days=30)


def _write_private(path: Path, key: ec.EllipticCurvePrivateKey) -> None:
    if path.exists():
        raise FileExistsError(path)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(pem)


def _write_cert(path: Path, cert: x509.Certificate) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def make_local_ca(out_dir: Path, name: str = "WorkPrinter Capture Local CA") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ca_crt, ca_key = out_dir / "ca.crt", out_dir / "ca.key"
    if ca_crt.exists() or ca_key.exists():
        raise FileExistsError(f"{ca_crt} or {ca_key} already exists")
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=3650 * 2))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    _write_private(ca_key, key)
    _write_cert(ca_crt, cert)
    return ca_crt, ca_key


def make_server_cert(
    ca_cert: Path,
    ca_key: Path,
    out_cert: Path,
    out_key: Path,
    hostnames: list[str],
    ips: list[str],
    days: int = SERVER_CERT_DAYS,
) -> None:
    if out_cert.exists() or out_key.exists():
        raise FileExistsError(f"{out_cert} or {out_key} already exists")
    ca = x509.load_pem_x509_certificate(ca_cert.read_bytes())
    signer = serialization.load_pem_private_key(ca_key.read_bytes(), password=None)
    der, spki = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    if signer.public_key().public_bytes(der, spki) != ca.public_key().public_bytes(der, spki):
        raise ValueError(f"{ca_key} does not match {ca_cert}")
    key = ec.generate_private_key(ec.SECP256R1())
    # Apple counts validity from notBefore, so `days` is measured from there.
    start = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=5)
    names: list[x509.GeneralName] = [x509.DNSName(h) for h in hostnames]
    names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0])]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + dt.timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca.public_key()), critical=False
        )
        .sign(signer, hashes.SHA256())
    )
    out_cert.parent.mkdir(parents=True, exist_ok=True)
    _write_private(out_key, key)
    try:
        _write_cert(out_cert, cert)
    except BaseException:
        # A key without its certificate would make the next attempt fail on "already exists".
        out_key.unlink(missing_ok=True)
        raise


def server_cert_not_after(cert_file: Path) -> dt.datetime:
    return x509.load_pem_x509_certificate(cert_file.read_bytes()).not_valid_after_utc


def server_cert_names(cert_file: Path) -> tuple[set[str], set[str]]:
    """The DNS names and IP addresses in the certificate's subjectAltName."""
    cert = x509.load_pem_x509_certificate(cert_file.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    dns = {n.lower() for n in san.get_values_for_type(x509.DNSName)}
    ips = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    return dns, ips


def renew_server_cert(ca_cert: Path, ca_key: Path, cert_file: Path, key_file: Path) -> dt.datetime:
    """Replace the server certificate and key with new ones for the same names, signed by the
    CA. The new pair is written under temporary names first, so a failure leaves the old pair
    in place. Returns the new certificate's expiry."""
    old = x509.load_pem_x509_certificate(cert_file.read_bytes())
    san = old.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    hosts = list(san.get_values_for_type(x509.DNSName))
    ips = [str(ip) for ip in san.get_values_for_type(x509.IPAddress)]
    if not hosts:
        raise ValueError(f"{cert_file} names no host; make a new one with wpcap gen-cert")
    replace_server_cert(ca_cert, ca_key, cert_file, key_file, hosts, ips)
    return server_cert_not_after(cert_file)


def replace_server_cert(
    ca_cert: Path, ca_key: Path, cert_file: Path, key_file: Path, hosts: list[str], ips: list[str]
) -> None:
    """Write a new server certificate and key under temporary names, then move them over the
    old pair, so a failure (a bad IP, a full disk) leaves the old pair in place."""
    new_cert = cert_file.with_name(cert_file.name + ".new")
    new_key = key_file.with_name(key_file.name + ".new")
    # Left by a renewal interrupted before its replace: never in use, safe to remove.
    new_cert.unlink(missing_ok=True)
    new_key.unlink(missing_ok=True)
    make_server_cert(ca_cert, ca_key, new_cert, new_key, hosts, ips)
    os.replace(new_key, key_file)
    os.replace(new_cert, cert_file)


def local_names() -> tuple[list[str], list[str]]:
    """Hostnames and IPv4 addresses this PC answers to, for the certificate.

    A PC whose hostname does not resolve (socket.gaierror) deliberately still gets
    a certificate for localhost and 127.0.0.1; the Tailscale and LAN addresses are
    added by the operator with `wpcap gen-cert --ip`.
    """
    host = socket.gethostname()
    hosts = [host, "localhost"]
    ips: list[str] = []
    try:
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except socket.gaierror:
        pass
    if "127.0.0.1" not in ips:
        ips.append("127.0.0.1")
    return hosts, ips
