"""Drive one Machine with simulated hardware, in virtual time (tests) or real time (demo)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from wpcap.clock import SimClock
from wpcap.clocksync import ClockSync
from wpcap.machine import Machine, MachineConfig, RecordingAlerter
from wpcap.sim.camera import SimCamera
from wpcap.sim.film import SimFilm
from wpcap.sim.syncbox import SimSyncBox
from wpcap.sim.transport import sim_transport_pair
from wpcap.synclink import SyncBoxLink


class SimRig:
    def __init__(
        self,
        config: MachineConfig,
        film: SimFilm,
        offset_us: int = 0,
        drift_ppm: float = 0.0,
        cam_fps: float = 60.0,
        cam_size: tuple[int, int] = (192, 108),
        free_bytes: Callable[[Path], int] | None = None,
    ) -> None:
        self.clock = SimClock()
        box_side, pc_side = sim_transport_pair()
        self.box = SimSyncBox(self.clock, box_side, offset_us=offset_us, drift_ppm=drift_ppm)
        self.camera = SimCamera(
            self.clock, film, fps=cam_fps, width=cam_size[0], height=cam_size[1]
        )
        self.alerter = RecordingAlerter()
        link = SyncBoxLink(pc_side, self.clock, ClockSync(), lambda ev: None, lambda s, t: None)
        kwargs = {} if free_bytes is None else {"free_bytes": free_bytes}
        self.machine = Machine(config, self.clock, link, self.camera, self.alerter, **kwargs)
        self.switch_times: list[int] = film.switch_times()
        self._next_switch = 0
        self.machine.start()

    @property
    def alerts(self) -> list[tuple[str, str, str]]:
        return self.alerter.alerts

    def _step(self) -> None:
        now = self.clock.now_ns()
        if self.camera.started:
            self.camera.emit_until(now)
        while (
            self._next_switch < len(self.switch_times)
            and self.switch_times[self._next_switch] <= now
        ):
            self.box.close_switch()
            self._next_switch += 1
        self.box.tick()
        self.machine.tick()
        saver = self.machine._saver
        if saver is not None and saver.alive:
            saver.join(5)

    def run_until(self, t_ns: int, step_ns: int = 1_000_000) -> None:
        while self.clock.now_ns() < t_ns:
            self.clock.advance(step_ns)
            self._step()

    def run_for(self, ns: int, step_ns: int = 1_000_000) -> None:
        self.run_until(self.clock.now_ns() + ns, step_ns)

    def run_realtime(self, seconds: float, step_ns: int = 2_000_000) -> None:
        """Demo Mode: advance the simulated clock in step with the wall clock."""
        start_wall = time.perf_counter_ns()
        start_sim = self.clock.now_ns()
        end = start_sim + round(seconds * 1e9)
        while self.clock.now_ns() < end:
            target = start_sim + (time.perf_counter_ns() - start_wall)
            if target > self.clock.now_ns():
                self.clock.set(min(target, end))
                self._step()
            else:
                time.sleep(step_ns / 1e9)
