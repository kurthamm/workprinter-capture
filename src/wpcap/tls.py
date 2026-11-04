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
    days: int = 3650,
) -> None:
    if out_cert.exists() or out_key.exists():
        raise FileExistsError(f"{out_cert} or {out_key} already exists")
    ca = x509.load_pem_x509_certificate(ca_cert.read_bytes())
    signer = serialization.load_pem_private_key(ca_key.read_bytes(), password=None)
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.UTC)
    names: list[x509.GeneralName] = [x509.DNSName(h) for h in hostnames]
    names += [x509.IPAddress(ipaddress.ip_address(ip)) for ip in ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostnames[0])]))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
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
    _write_cert(out_cert, cert)


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
