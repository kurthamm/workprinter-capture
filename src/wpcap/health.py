"""PC health for the page: CPU, memory and, where the OS exposes it, a temperature."""

from __future__ import annotations

import psutil


def cpu_temperature_c() -> float | None:
    """Highest current CPU temperature the OS reports, or None when it reports none
    (Windows without vendor sensor drivers). Never guesses."""
    if not hasattr(psutil, "sensors_temperatures"):
        return None
    temps = psutil.sensors_temperatures()
    readings = [
        e.current
        for name, entries in temps.items()
        if name in ("coretemp", "k10temp", "cpu_thermal", "zenpower")
        for e in entries
        if e.current is not None and 0.0 < e.current < 150.0
    ]
    return max(readings) if readings else None


def pc_health() -> dict:
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "memory_percent": psutil.virtual_memory().percent,
        "temperature_c": cpu_temperature_c(),
    }
