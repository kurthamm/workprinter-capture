from wpcap.health import pc_health


def test_pc_health_has_the_three_keys_and_sane_values():
    h = pc_health()
    assert set(h) == {"cpu_percent", "memory_percent", "temperature_c"}
    assert 0.0 <= h["cpu_percent"] <= 100.0
    assert 0.0 < h["memory_percent"] < 100.0
    assert h["temperature_c"] is None or 0.0 < h["temperature_c"] < 150.0


def test_temperature_is_none_when_os_reports_none(monkeypatch):
    import psutil

    monkeypatch.setattr(psutil, "sensors_temperatures", lambda: {}, raising=False)
    assert pc_health()["temperature_c"] is None


def test_temperature_is_none_when_psutil_has_no_sensors(monkeypatch):
    import psutil

    monkeypatch.delattr(psutil, "sensors_temperatures", raising=False)
    assert pc_health()["temperature_c"] is None
