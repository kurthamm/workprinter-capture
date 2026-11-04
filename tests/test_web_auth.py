import time

from wpcap.web.auth import check_token, make_token


def test_token_roundtrip_and_tamper():
    t = make_token("s" * 64, issued=time.time())
    assert check_token("s" * 64, t, max_age_s=60)
    assert not check_token("x" * 64, t, max_age_s=60)
    assert not check_token("s" * 64, t[:-1] + ("0" if t[-1] != "0" else "1"), max_age_s=60)
    assert not check_token("s" * 64, "garbage", max_age_s=60)


def test_token_expires():
    t = make_token("s" * 64, issued=time.time() - 100)
    assert not check_token("s" * 64, t, max_age_s=60)
    assert check_token("s" * 64, t, max_age_s=200)


def test_non_ascii_or_malformed_token_is_rejected():
    assert check_token("s" * 64, "1.é", 60) is False
    assert check_token("s" * 64, "x.abc", 60) is False
    assert check_token("s" * 64, "1.2.3", 60) is False


def test_overlong_stamp_is_rejected_not_an_error():
    assert check_token("s" * 64, "9" * 5000 + ".abc", 60) is False
    assert check_token("s" * 64, "1" * 21 + ".abc", 60) is False
