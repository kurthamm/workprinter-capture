"""wpcap.toml: the one configuration file. Every field is required unless stated; a missing
or wrong field stops the program at startup with a message naming it (fail fast)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import tomllib
from dataclasses import dataclass
from pathlib import Path

from wpcap.reel import ReelFolder

FILM_TYPES = ("super8", "regular8")
MACHINE_KINDS = ("sim",)  # plans 3 and 4 add "serial"
_SERVER_KEYS = {"host", "port", "password_hash", "secret", "cert_file", "key_file"}
_MACHINE_KEYS = {"name", "kind", "reel_root", "delay_ms", "debounce_us", "film_type", "sim_frames"}
_NTFY_KEYS = {"url", "topic"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    password_hash: str
    secret: str
    cert_file: Path
    key_file: Path


@dataclass(frozen=True)
class NtfyConfig:
    url: str
    topic: str


@dataclass(frozen=True)
class MachineSpec:
    name: str
    kind: str
    reel_root: Path
    delay_ms: float
    debounce_us: int
    film_type: str
    sim_frames: int


@dataclass(frozen=True)
class AppConfig:
    server: ServerConfig
    machines: list[MachineSpec]
    ntfy: NtfyConfig | None


# ---- passwords -----------------------------------------------------------------------------

_SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time; a malformed stored value is simply 'no match'."""
    try:
        algo, salt_hex, key_hex = stored.split("$")
        if algo != "scrypt":
            return False
        salt, key = bytes.fromhex(salt_hex), bytes.fromhex(key_hex)
    except ValueError:
        return False
    if len(key) != _SCRYPT["dklen"]:
        return False
    candidate = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return hmac.compare_digest(candidate, key)


def new_secret() -> str:
    return secrets.token_hex(32)


# ---- loading -------------------------------------------------------------------------------


def _section(data: dict, name: str, keys: set[str]) -> dict:
    sec = data.get(name)
    if not isinstance(sec, dict):
        raise ConfigError(f"missing [{name}] section")
    unknown = set(sec) - keys
    if unknown:
        raise ConfigError(f"unknown key(s) in [{name}]: {', '.join(sorted(unknown))}")
    missing = keys - set(sec)
    if missing:
        raise ConfigError(f"missing {name}.{sorted(missing)[0]}")
    return sec


def _typed(sec: dict, where: str, key: str, typ: type) -> object:
    v = sec[key]
    if typ is float and isinstance(v, int) and not isinstance(v, bool):
        v = float(v)
    if not isinstance(v, typ) or isinstance(v, bool):
        raise ConfigError(f"{where}.{key} must be {typ.__name__}, got {v!r}")
    return v


def _server(data: dict) -> ServerConfig:
    s = _section(data, "server", _SERVER_KEYS)
    port = _typed(s, "server", "port", int)
    if not 1 <= port <= 65535:
        raise ConfigError(f"server.port out of range: {port}")
    for k in ("host", "password_hash", "secret", "cert_file", "key_file"):
        _typed(s, "server", k, str)
    if not s["password_hash"].startswith("scrypt$"):
        raise ConfigError("server.password_hash is not an scrypt hash (run: wpcap hash-password)")
    if len(s["secret"]) < 32:
        raise ConfigError("server.secret must be at least 32 characters (run: wpcap init-config)")
    return ServerConfig(
        host=s["host"],
        port=port,
        password_hash=s["password_hash"],
        secret=s["secret"],
        cert_file=Path(s["cert_file"]),
        key_file=Path(s["key_file"]),
    )


def _ntfy(data: dict) -> NtfyConfig | None:
    if "ntfy" not in data:
        return None
    n = _section(data, "ntfy", _NTFY_KEYS)
    _typed(n, "ntfy", "url", str)
    _typed(n, "ntfy", "topic", str)
    if not n["url"].startswith(("http://", "https://")):
        raise ConfigError(f"ntfy.url must start with http:// or https://, got {n['url']!r}")
    return NtfyConfig(url=n["url"].rstrip("/"), topic=n["topic"])


def _machine(i: int, m: object) -> MachineSpec:
    where = f"machine[{i}]"
    if not isinstance(m, dict):
        raise ConfigError(f"{where} must be a table")
    unknown = set(m) - _MACHINE_KEYS
    if unknown:
        raise ConfigError(f"unknown key(s) in {where}: {', '.join(sorted(unknown))}")
    missing = _MACHINE_KEYS - set(m)
    if missing:
        raise ConfigError(f"missing {where}.{sorted(missing)[0]}")
    name = _typed(m, where, "name", str)
    try:
        ReelFolder.check_name(name)
    except ValueError as e:
        raise ConfigError(f"{where}.name: {e}") from e
    kind = _typed(m, where, "kind", str)
    if kind not in MACHINE_KINDS:
        raise ConfigError(f"{where}.kind must be one of {MACHINE_KINDS}, got {kind!r}")
    film_type = _typed(m, where, "film_type", str)
    if film_type not in FILM_TYPES:
        raise ConfigError(f"{where}.film_type must be one of {FILM_TYPES}, got {film_type!r}")
    delay_ms = _typed(m, where, "delay_ms", float)
    if not 0.0 <= delay_ms <= 500.0:
        raise ConfigError(f"{where}.delay_ms must be 0..500")
    debounce_us = _typed(m, where, "debounce_us", int)
    if not 1000 <= debounce_us <= 100_000:
        raise ConfigError(f"{where}.debounce_us must be 1000..100000")
    sim_frames = _typed(m, where, "sim_frames", int)
    if sim_frames < 1:
        raise ConfigError(f"{where}.sim_frames must be at least 1")
    return MachineSpec(
        name=name,
        kind=kind,
        reel_root=Path(_typed(m, where, "reel_root", str)),
        delay_ms=delay_ms,
        debounce_us=debounce_us,
        film_type=film_type,
        sim_frames=sim_frames,
    )


def load_config(path: Path) -> AppConfig:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise ConfigError(f"config file not found: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e
    unknown = set(data) - {"server", "ntfy", "machine"}
    if unknown:
        raise ConfigError(f"unknown top-level key(s): {', '.join(sorted(unknown))}")
    server = _server(data)
    ntfy = _ntfy(data)
    raw = data.get("machine")
    if not isinstance(raw, list) or not raw:
        raise ConfigError("at least one [[machine]] is required")
    machines = [_machine(i, m) for i, m in enumerate(raw)]
    names = [m.name for m in machines]
    for n in names:
        if names.count(n) > 1:
            raise ConfigError(f"machine name used twice: {n!r}")
    roots = [m.reel_root.resolve() for m in machines]
    for i, r in enumerate(roots):
        if roots.index(r) != i:
            raise ConfigError(
                f"reel_root shared by {machines[roots.index(r)].name!r} and {machines[i].name!r}: "
                "each machine needs its own reel folder"
            )
    return AppConfig(server=server, machines=machines, ntfy=ntfy)


def sample_config(
    password_hash: str, reel_root: Path, cert_file: Path, key_file: Path, secret: str
) -> str:
    r1, r2 = (reel_root / "WorkPrinter 1").as_posix(), (reel_root / "WorkPrinter 2").as_posix()
    return f'''# WorkPrinter Capture configuration. Edit, then: wpcap serve --config wpcap.toml
[server]
host = "0.0.0.0"          # listen on every network interface of this PC (home network only)
port = 8443
password_hash = "{password_hash}"
secret = "{secret}"
cert_file = "{cert_file.as_posix()}"
key_file = "{key_file.as_posix()}"

# Phone alerts through a self-hosted ntfy server (optional): remove the # to enable.
#[ntfy]
#url = "http://127.0.0.1:2586"
#topic = "workprinter"

[[machine]]
name = "WorkPrinter 1"
kind = "sim"              # simulated film and sync box (Demo Mode)
reel_root = "{r1}"
delay_ms = 40.0
debounce_us = 20000
film_type = "super8"
sim_frames = 300

[[machine]]
name = "WorkPrinter 2"
kind = "sim"
reel_root = "{r2}"
delay_ms = 40.0
debounce_us = 20000
film_type = "regular8"
sim_frames = 300
'''
