from wpcap.health import pc_health


def test_pc_health_has_the_three_keys_and_sane_values():
    h = pc_health()
    assert set(h) == {"cpu_percent", "memory_percent", "temperature_c"}
    assert 0.0 <= h["cpu_percent"] <= 100.0
    assert 0.0 < h["memory_percent"] < 100.0
    assert h["temperature_c"] is None or 0.0 < h["temperature_c"] < 150.0
