import pytest

from wpcap.protocol import (
    Bounce,
    Click,
    Hello,
    ProtocolError,
    SequenceChecker,
    SequenceGapError,
    TimeReply,
    cmd_identify,
    cmd_set_debounce,
    cmd_time_request,
    crc16,
    decode_line,
    encode_message,
    parse_command,
)


def test_crc16_ccitt_false_check_value():
    # Standard check value for CRC-16/CCITT-FALSE over "123456789".
    assert crc16(b"123456789") == 0x29B1


@pytest.mark.parametrize(
    "msg",
    [
        Click(seq=7, t_us=1_234_567, interval_us=125_000),
        Bounce(seq=8, t_us=1_240_000),
        TimeReply(seq=9, t_us=1_250_000, req_id=42),
        Hello(seq=0, t_us=5, fw_version="0.1.0", serial="E6614C311B4C7A2F"),
    ],
)
def test_round_trip(msg):
    line = encode_message(msg)
    assert line.endswith(b"\n")
    assert decode_line(line) == msg


def test_click_wire_format_is_exact():
    line = encode_message(Click(seq=1, t_us=2, interval_us=3))
    body = b"C 1 2 3"
    assert line == body + b"*" + f"{crc16(body):04X}".encode() + b"\n"


def test_bad_crc_is_protocol_error():
    line = bytearray(encode_message(Click(seq=1, t_us=2, interval_us=3)))
    line[-2] = ord("0") if line[-2] != ord("0") else ord("1")
    with pytest.raises(ProtocolError, match="CRC"):
        decode_line(bytes(line))


def test_unknown_type_and_wrong_field_count_are_protocol_errors():
    body = b"X 1 2"
    with pytest.raises(ProtocolError, match="unknown"):
        decode_line(body + b"*" + f"{crc16(body):04X}".encode() + b"\n")
    body = b"C 1 2"
    with pytest.raises(ProtocolError, match="fields"):
        decode_line(body + b"*" + f"{crc16(body):04X}".encode() + b"\n")


def test_non_integer_field_is_protocol_error():
    body = b"C 1 two 3"
    with pytest.raises(ProtocolError, match="integer"):
        decode_line(body + b"*" + f"{crc16(body):04X}".encode() + b"\n")


def test_sequence_checker_accepts_consecutive_and_wraps():
    s = SequenceChecker()
    s.check(2**32 - 2)
    s.check(2**32 - 1)
    s.check(0)


def test_sequence_gap_and_repeat_raise():
    s = SequenceChecker()
    s.check(5)
    with pytest.raises(SequenceGapError) as e:
        s.check(7)
    assert (e.value.expected, e.value.got) == (6, 7)
    s2 = SequenceChecker()
    s2.check(5)
    with pytest.raises(SequenceGapError):
        s2.check(5)


def test_commands_round_trip():
    assert parse_command(cmd_time_request(42)) == ("T", [42])
    assert parse_command(cmd_set_debounce(20_000)) == ("D", [20_000])
    assert parse_command(cmd_identify()) == ("I", [])


def test_command_with_bad_crc_is_protocol_error():
    line = bytearray(cmd_time_request(1))
    line[-2] = ord("0") if line[-2] != ord("0") else ord("1")
    with pytest.raises(ProtocolError, match="CRC"):
        parse_command(bytes(line))
