import re
from pathlib import Path

import pytest

from wpcap.config import (
    ConfigError,
    hash_password,
    load_config,
    new_secret,
    sample_config,
    verify_password,
)


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "wpcap.toml"
    p.write_text(text, encoding="utf-8")
    return p


def good(tmp_path: Path, **over) -> str:
    base = dict(
        host="127.0.0.1",
        port=8443,
        ph=hash_password("pw"),
        secret=new_secret(),
        cert=(tmp_path / "c.crt").as_posix(),
        key=(tmp_path / "c.key").as_posix(),
        reels1=(tmp_path / "r1").as_posix(),
        reels2=(tmp_path / "r2").as_posix(),
        name2="WorkPrinter 2",
    )
    base.update(over)
    return f"""
[server]
host = "{base['host']}"
port = {base['port']}
password_hash = "{base['ph']}"
secret = "{base['secret']}"
cert_file = "{base['cert']}"
key_file = "{base['key']}"

[[machine]]
name = "WorkPrinter 1"
kind = "sim"
reel_root = "{base['reels1']}"
delay_ms = 40.0
debounce_us = 20000
film_type = "super8"
sim_frames = 120

[[machine]]
name = "{base['name2']}"
kind = "sim"
reel_root = "{base['reels2']}"
delay_ms = 40.0
debounce_us = 20000
film_type = "regular8"
sim_frames = 120
"""


def test_password_hash_roundtrip_and_format():
    h = hash_password("correct horse")
    assert h.startswith("scrypt$") and h.count("$") == 2
    assert verify_password("correct horse", h)
    assert not verify_password("wrong", h)
    assert hash_password("correct horse") != h  # new salt each time


def test_verify_rejects_malformed_stored_hash():
    assert not verify_password("x", "not-a-hash")
    assert not verify_password("x", "scrypt$zz$zz")


def test_load_good_config(tmp_path):
    c = load_config(write(tmp_path, good(tmp_path)))
    assert c.server.port == 8443 and c.server.host == "127.0.0.1"
    assert [m.name for m in c.machines] == ["WorkPrinter 1", "WorkPrinter 2"]
    assert c.machines[1].film_type == "regular8" and c.machines[0].sim_frames == 120
    assert c.machines[0].reel_root == tmp_path / "r1"
    assert c.ntfy is None


def test_ntfy_section_is_optional_but_complete(tmp_path):
    text = good(tmp_path) + '\n[ntfy]\nurl = "http://127.0.0.1:2586"\ntopic = "wp"\n'
    assert load_config(write(tmp_path, text)).ntfy.topic == "wp"
    with pytest.raises(ConfigError, match="ntfy.topic"):
        load_config(write(tmp_path, good(tmp_path) + '\n[ntfy]\nurl = "http://x"\n'))


@pytest.mark.parametrize(
    "field",
    ["password_hash", "secret", "cert_file", "key_file", "host", "port"],
)
def test_missing_server_field_names_it(tmp_path, field):
    text = "\n".join(line for line in good(tmp_path).splitlines() if not line.startswith(field))
    with pytest.raises(ConfigError, match=f"server.{field}"):
        load_config(write(tmp_path, text))


def test_duplicate_machine_names_rejected(tmp_path):
    with pytest.raises(ConfigError, match="WorkPrinter 1"):
        load_config(write(tmp_path, good(tmp_path, name2="WorkPrinter 1")))


def test_shared_reel_root_rejected(tmp_path):
    with pytest.raises(ConfigError, match="reel_root"):
        load_config(write(tmp_path, good(tmp_path, reels2=(tmp_path / "r1").as_posix())))


def test_bad_machine_name_rejected(tmp_path):
    with pytest.raises(ConfigError, match="name"):
        load_config(write(tmp_path, good(tmp_path, name2="CON")))


def test_unknown_kind_and_bad_film_type_rejected(tmp_path):
    with pytest.raises(ConfigError, match="kind"):
        load_config(write(tmp_path, good(tmp_path).replace('kind = "sim"', 'kind = "usb"', 1)))
    with pytest.raises(ConfigError, match="film_type"):
        load_config(write(tmp_path, good(tmp_path).replace("regular8", "16mm")))


def test_no_machines_rejected(tmp_path):
    text = good(tmp_path).split("[[machine]]")[0]
    with pytest.raises(ConfigError, match="machine"):
        load_config(write(tmp_path, text))


def test_unknown_key_rejected(tmp_path):
    with pytest.raises(ConfigError, match="colour"):
        text = good(tmp_path).replace("port = 8443", 'port = 8443\ncolour = "red"')
        load_config(write(tmp_path, text))


def test_sample_config_loads(tmp_path):
    text = sample_config(
        hash_password("pw"),
        tmp_path / "reels",
        tmp_path / "c.crt",
        tmp_path / "c.key",
        new_secret(),
    )
    c = load_config(write(tmp_path, text))
    assert len(c.machines) == 2 and all(m.kind == "sim" for m in c.machines)
    assert c.machines[0].reel_root != c.machines[1].reel_root


def test_verify_never_raises_on_garbage():
    h = hash_password("pw")
    assert not verify_password("\ud800", h)
    assert not verify_password("pw", None)  # type: ignore[arg-type]
    assert not verify_password("pw", 123)  # type: ignore[arg-type]
    assert not verify_password("pw", "scrypt$" + "00" * 16 + "$" + "00" * 8)  # short key
    assert not verify_password("pw", "scrypt$$" + "00" * 32)  # empty salt
    assert not verify_password("pw", "scrypt$00$00$00")  # too many parts


def test_malformed_password_hash_rejected_at_load(tmp_path):
    bad = hash_password("pw")
    for broken in ("scrypt$zz$zz", "scrypt$00$00", bad + "$x"):
        with pytest.raises(ConfigError, match="server.password_hash"):
            load_config(write(tmp_path, good(tmp_path, ph=broken)))


@pytest.mark.parametrize(
    "field, line",
    [
        ("server.host", 'host = ""'),
        ("server.cert_file", 'cert_file = ""'),
        ("server.key_file", 'key_file = "  "'),
        ("machine[0].reel_root", 'reel_root = ""'),
    ],
)
def test_empty_strings_rejected_naming_the_field(tmp_path, field, line):
    key = line.split(" ")[0]
    lines = good(tmp_path).splitlines()
    i = next(i for i, x in enumerate(lines) if x.startswith(key + " "))
    lines[i] = line
    with pytest.raises(ConfigError, match=re.escape(field)):
        load_config(write(tmp_path, "\n".join(lines)))


def test_empty_ntfy_topic_rejected(tmp_path):
    text = good(tmp_path) + '\n[ntfy]\nurl = "http://127.0.0.1:2586"\ntopic = ""\n'
    with pytest.raises(ConfigError, match="ntfy.topic"):
        load_config(write(tmp_path, text))


def test_relative_reel_root_rejected(tmp_path):
    with pytest.raises(ConfigError, match=r"machine\[1\].reel_root must be an absolute path"):
        load_config(write(tmp_path, good(tmp_path, reels2="reels/two")))


def test_sample_config_needs_absolute_paths(tmp_path):
    with pytest.raises(ValueError, match="reel_root"):
        sample_config(
            hash_password("pw"), Path("reels"), tmp_path / "c", tmp_path / "k", new_secret()
        )
