import datetime as dt
import ssl

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from wpcap.tls import local_names, make_local_ca, make_server_cert


def test_ca_and_server_cert_chain_and_names(tmp_path):
    ca_crt, ca_key = make_local_ca(tmp_path)
    assert ca_crt.exists() and ca_key.exists()
    crt, key = tmp_path / "wpcap.crt", tmp_path / "wpcap.key"
    make_server_cert(
        ca_crt, ca_key, crt, key, ["scanpc", "localhost"], ["127.0.0.1", "192.168.50.87"]
    )
    cert = x509.load_pem_x509_certificate(crt.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert set(san.get_values_for_type(x509.DNSName)) == {"scanpc", "localhost"}
    ips = {str(ip) for ip in san.get_values_for_type(x509.IPAddress)}
    assert ips == {"127.0.0.1", "192.168.50.87"}
    ca = x509.load_pem_x509_certificate(ca_crt.read_bytes())
    assert cert.issuer == ca.subject
    ca.public_key().verify(
        cert.signature, cert.tbs_certificate_bytes, cert.signature_algorithm_parameters
    )
    # Apple devices refuse server certificates valid for more than 825 days
    valid = cert.not_valid_after_utc - cert.not_valid_before_utc
    assert dt.timedelta(days=800) < valid <= dt.timedelta(days=825)
    # the private key is readable by the TLS stack
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)
    # the CA is a CA; the server cert is not
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is True
    assert cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca is False


def test_never_overwrites(tmp_path):
    make_local_ca(tmp_path)
    with pytest.raises(FileExistsError):
        make_local_ca(tmp_path)
    crt, key = tmp_path / "s.crt", tmp_path / "s.key"
    make_server_cert(tmp_path / "ca.crt", tmp_path / "ca.key", crt, key, ["a"], [])
    with pytest.raises(FileExistsError):
        make_server_cert(tmp_path / "ca.crt", tmp_path / "ca.key", crt, key, ["a"], [])


def test_private_keys_are_unencrypted_pem_and_not_world_readable_on_posix(tmp_path):
    import os
    import stat

    _, ca_key = make_local_ca(tmp_path)
    serialization.load_pem_private_key(ca_key.read_bytes(), password=None)
    if os.name == "posix":
        assert stat.S_IMODE(ca_key.stat().st_mode) == 0o600


def test_local_names_include_hostname_and_localhost():
    hosts, ips = local_names()
    assert "localhost" in hosts and len(hosts) >= 2
    assert all(ip.count(".") == 3 for ip in ips)


def _san(crt):
    cert = x509.load_pem_x509_certificate(crt.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return set(san.get_values_for_type(x509.DNSName)), {
        str(ip) for ip in san.get_values_for_type(x509.IPAddress)
    }


def test_serve_renews_a_certificate_expiring_soon(tmp_path, capsys):
    from wpcap.__main__ import renew_cert_if_expiring

    ca_crt, ca_key = make_local_ca(tmp_path)
    crt, key = tmp_path / "wpcap.crt", tmp_path / "wpcap.key"
    make_server_cert(ca_crt, ca_key, crt, key, ["scanpc", "localhost"], ["10.0.0.5"], days=10)
    names = _san(crt)
    renew_cert_if_expiring(crt, key)
    out = capsys.readouterr().out
    assert "renewed certificate, valid until" in out
    cert = x509.load_pem_x509_certificate(crt.read_bytes())
    assert cert.not_valid_after_utc - dt.datetime.now(dt.UTC) > dt.timedelta(days=800)
    assert _san(crt) == names
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(crt, key)  # key matches cert
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "ca.crt", "ca.key", "wpcap.crt", "wpcap.key", "wpcap.lock"
    ]
    # a fresh certificate is left alone
    before = crt.read_bytes()
    renew_cert_if_expiring(crt, key)
    assert crt.read_bytes() == before and capsys.readouterr().out == ""


def test_serve_warns_when_no_ca_can_renew_the_certificate(tmp_path, capsys):
    from wpcap.__main__ import renew_cert_if_expiring

    ca_dir, certs = tmp_path / "ca", tmp_path / "certs"
    ca_crt, ca_key = make_local_ca(ca_dir)
    crt, key = certs / "wpcap.crt", certs / "wpcap.key"
    make_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [], days=10)
    before = crt.read_bytes()
    renew_cert_if_expiring(crt, key)
    err = capsys.readouterr().err
    assert "wpcap gen-cert --replace" in err and str(crt) in err
    assert crt.read_bytes() == before


def test_failed_certificate_write_removes_the_new_key(tmp_path, monkeypatch):
    from wpcap import tls

    ca_crt, ca_key = make_local_ca(tmp_path)

    def boom(path, cert):
        raise OSError("disk full")

    monkeypatch.setattr(tls, "_write_cert", boom)
    crt, key = tmp_path / "wpcap.crt", tmp_path / "wpcap.key"
    with pytest.raises(OSError, match="disk full"):
        make_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [])
    assert not key.exists() and not crt.exists()


def test_failed_renewal_keeps_a_still_valid_certificate(tmp_path, capsys, monkeypatch):
    import wpcap.__main__ as cli

    ca_crt, ca_key = make_local_ca(tmp_path)
    crt, key = tmp_path / "wpcap.crt", tmp_path / "wpcap.key"
    make_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [], days=10)
    before = crt.read_bytes()

    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(cli, "renew_server_cert", broken)
    cli.renew_cert_if_expiring(crt, key)
    err = capsys.readouterr().err
    assert "could not renew" in err and "disk full" in err and "wpcap gen-cert --replace" in err
    assert crt.read_bytes() == before


def test_failed_renewal_of_an_expired_certificate_stops_startup(tmp_path, monkeypatch):
    import wpcap.__main__ as cli

    ca_crt, ca_key = make_local_ca(tmp_path)
    crt, key = tmp_path / "wpcap.crt", tmp_path / "wpcap.key"
    make_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [], days=0)  # expired 5 min ago

    def broken(*args):
        raise OSError("disk full")

    monkeypatch.setattr(cli, "renew_server_cert", broken)
    with pytest.raises(OSError, match="disk full"):
        cli.renew_cert_if_expiring(crt, key)


def test_a_ca_key_that_does_not_match_the_ca_certificate_is_refused(tmp_path):
    ca_crt, _ = make_local_ca(tmp_path / "a")
    _, other_key = make_local_ca(tmp_path / "b")
    with pytest.raises(ValueError, match="does not match"):
        make_server_cert(ca_crt, other_key, tmp_path / "s.crt", tmp_path / "s.key", ["h"], [])
    assert not (tmp_path / "s.crt").exists() and not (tmp_path / "s.key").exists()


def test_server_cert_names_lists_dns_names_and_addresses(tmp_path):
    from wpcap.tls import server_cert_names

    ca_crt, ca_key = make_local_ca(tmp_path)
    crt = tmp_path / "s.crt"
    make_server_cert(ca_crt, ca_key, crt, tmp_path / "s.key", ["Scanpc"], ["192.168.1.5"])
    assert server_cert_names(crt) == ({"scanpc"}, {"192.168.1.5"})


def test_failed_ca_write_leaves_no_partial_ca_files(tmp_path, monkeypatch):
    from wpcap import tls

    def boom(path, cert):
        raise OSError("disk full")

    monkeypatch.setattr(tls, "_write_cert", boom)
    with pytest.raises(OSError, match="disk full"):
        make_local_ca(tmp_path)
    assert not (tmp_path / "ca.key").exists() and not (tmp_path / "ca.crt").exists()


def test_expired_certificate_without_a_ca_stops_startup(tmp_path):
    from wpcap.__main__ import renew_cert_if_expiring

    ca_dir, certs = tmp_path / "ca", tmp_path / "certs"
    ca_crt, ca_key = make_local_ca(ca_dir)
    crt, key = certs / "wpcap.crt", certs / "wpcap.key"
    make_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [], days=0)  # expired 5 min ago
    with pytest.raises(RuntimeError, match=r"expired .* no CA .* wpcap gen-cert --replace"):
        renew_cert_if_expiring(crt, key)


def test_mismatched_key_and_certificate_name_the_fix(tmp_path):
    from wpcap.tls import check_server_pair

    ca_crt, ca_key = make_local_ca(tmp_path)
    make_server_cert(ca_crt, ca_key, tmp_path / "a.crt", tmp_path / "a.key", ["scanpc"], [])
    make_server_cert(ca_crt, ca_key, tmp_path / "b.crt", tmp_path / "b.key", ["scanpc"], [])
    check_server_pair(tmp_path / "a.crt", tmp_path / "a.key", tmp_path)
    with pytest.raises(ValueError, match="gen-cert --certs .* --replace"):
        check_server_pair(tmp_path / "a.crt", tmp_path / "b.key", tmp_path)


def test_a_second_replacement_in_the_same_folder_fails_fast(tmp_path):
    from wpcap.tls import _replace_lock, replace_server_cert

    ca_crt, ca_key = make_local_ca(tmp_path)
    crt, key = tmp_path / "wpcap.crt", tmp_path / "wpcap.key"
    make_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [])
    before = crt.read_bytes()
    with _replace_lock(tmp_path):
        with pytest.raises(RuntimeError, match="another certificate replacement"):
            replace_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [])
    assert crt.read_bytes() == before
    replace_server_cert(ca_crt, ca_key, crt, key, ["scanpc"], [])  # lock released
    assert crt.read_bytes() != before
