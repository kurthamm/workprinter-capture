"""Login: one password (scrypt hash in the config) and a signed, expiring session cookie."""

from __future__ import annotations

import hashlib
import hmac
import time

COOKIE = "wpcap_session"
SESSION_DAYS = 30


def make_token(secret: str, issued: float) -> str:
    stamp = f"{int(issued)}"
    sig = hmac.new(secret.encode(), stamp.encode(), hashlib.sha256).hexdigest()
    return f"{stamp}.{sig}"


def check_token(secret: str, token: str, max_age_s: float) -> bool:
    try:
        stamp, sig = token.split(".")
        issued = int(stamp)
    except ValueError:
        return False
    expected = hmac.new(secret.encode(), stamp.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False
    return time.time() - issued <= max_age_s
