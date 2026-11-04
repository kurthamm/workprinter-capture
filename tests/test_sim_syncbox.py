from wpcap.clock import SimClock
from wpcap.protocol import (
    Bounce,
    Click,
    Hello,
    TimeReply,
    cmd_identify,
    cmd_time_request,
    decode_line,
)
from wpcap.sim.syncbox import SimSyncBox
from wpcap.sim.transport import sim_transport_pair


def make():
    clock = SimClock()
    box_side, pc_side = sim_transport_pair()
    box = SimSyncBox(clock, box_side, offset_us=1_000_000)
    return clock, box, pc_side


def read_all(t):
    out = []
    while (line := t.read_line()) is not None:
        out.append(decode_line(line))
    return out


def test_hello_on_first_tick_then_every_second():
    clock, box, pc = make()
    box.tick()
    msgs = read_all(pc)
    assert len(msgs) == 1 and isinstance(msgs[0], Hello) and msgs[0].serial == "SIM00000001"
    clock.advance(500_000_000)
    box.tick()
    assert read_all(pc) == []
    clock.advance(600_000_000)
    box.tick()
    assert isinstance(read_all(pc)[0], Hello)


def test_clicks_and_bounce_with_sequence_numbers():
    clock, box, pc = make()
    box.tick()  # hello is seq 1
    read_all(pc)
    box.close_switch()
    clock.advance(5_000_000)  # 5 ms later: bounce
    box.close_switch()
    clock.advance(120_000_000)  # 125 ms after first: real click
    box.close_switch()
    msgs = read_all(pc)
    assert [type(m) for m in msgs] == [Click, Bounce, Click]
    assert [m.seq for m in msgs] == [2, 3, 4]
    assert msgs[0].interval_us == 0
    assert msgs[2].interval_us == 125_000
    assert msgs[0].t_us == box.box_time_us() - 125_000


def test_time_request_is_answered_with_box_time_and_req_id():
    clock, box, pc = make()
    clock.set(2_000_000_000)
    pc.write(cmd_time_request(77))
    box.tick()
    msgs = [m for m in read_all(pc) if isinstance(m, TimeReply)]
    assert len(msgs) == 1 and msgs[0].t_us == 3_000_000 and msgs[0].req_id == 77


def test_identify_answers_hello():
    clock, box, pc = make()
    box.tick()
    read_all(pc)
    pc.write(cmd_identify())
    box.tick()
    assert isinstance(read_all(pc)[0], Hello)


def test_drift_changes_box_time():
    clock = SimClock()
    box_side, _ = sim_transport_pair()
    box = SimSyncBox(clock, box_side, drift_ppm=100)
    clock.set(10_000_000_000)
    assert box.box_time_us() == 10_001_000


def test_sim_box_rejects_serial_the_wire_cannot_carry():
    import pytest

    clock = SimClock()
    box_side, _ = sim_transport_pair()
    with pytest.raises(ValueError):
        SimSyncBox(clock, box_side, serial="SIM 0001")
    with pytest.raises(ValueError):
        SimSyncBox(clock, box_side, fw_version="sim*0.1")
