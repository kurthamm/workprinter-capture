"""Login: one password (scrypt hash in the config) and a signed, expiring session cookie."""

from __future__ import annotations

import hashlib
import hmac
import re
import time

COOKIE = "wpcap_session"
SESSION_DAYS = 30
_TOKEN_RE = re.compile(r"[0-9]+\.[0-9a-f]+", re.ASCII)


def make_token(secret: str, issued: float) -> str:
    stamp = f"{int(issued)}"
    sig = hmac.new(secret.encode(), stamp.encode(), hashlib.sha256).hexdigest()
    return f"{stamp}.{sig}"


def check_token(secret: str, token: str, max_age_s: float) -> bool:
    if not _TOKEN_RE.fullmatch(token):
        return False
    stamp, sig = token.split(".")
    # A real stamp is a Unix time (10 digits); a huge one would make int() itself fail.
    if len(stamp) > 20:
        return False
    issued = int(stamp)
    expected = hmac.new(secret.encode(), stamp.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    return time.time() - issued <= max_age_s
