"""A Runner keeps one machine alive on its own thread. This plan ships the simulated one;
plans 3 and 4 add a runner for a serial sync box and a Windows camera."""

from __future__ import annotations

import threading
import traceback
from typing import Protocol

from wpcap.config import SIM_MIN_FRAMES, MachineSpec
from wpcap.machine import Alerter, Machine, MachineConfig, MachineState, ReelMeta
from wpcap.sim.film import SimFilm
from wpcap.sim.rig import SimRig

S = 1_000_000_000


class _NewReelJob:
    """A New Reel handed to the runner thread; the caller waits for its outcome."""

    def __init__(self, meta: ReelMeta) -> None:
        self.meta = meta
        self.done = threading.Event()
        self.error: Exception | None = None


class Runner(Protocol):
    machine: Machine

    def start(self) -> None: ...

    def stop(self) -> None: ...

    @property
    def alive(self) -> bool: ...

    @property
    def error(self) -> str | None: ...


class SimRunner:
    STOP_TIMEOUT_S = 10.0

    def __init__(self, spec: MachineSpec, alerter: Alerter, free_bytes=None) -> None:
        self.spec = spec
        self._alerter = alerter
        config = MachineConfig(
            name=spec.name,
            reel_root=spec.reel_root,
            delay_ms=spec.delay_ms,
            debounce_us=spec.debounce_us,
            gate_min_frames=SIM_MIN_FRAMES,
            gate_empty_needed=8,
        )
        self.rig = SimRig(config, self._film(0), alerter=alerter, free_bytes=free_bytes)
        self.machine: Machine = self.rig.machine
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"runner {spec.name}", daemon=True)
        self._error: str | None = None
        self._started = False
        self._pending_lock = threading.Lock()
        self._pending_job: _NewReelJob | None = None

    def _film(self, now_ns: int) -> SimFilm:
        return SimFilm(frames=self.spec.sim_frames, start_ns=now_ns + 3 * S)

    def start(self) -> None:
        if self._started:
            raise RuntimeError("runner already started")
        self._started = True
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                with self._pending_lock:
                    job, self._pending_job = self._pending_job, None
                if job is not None:
                    self._apply(job)
                self.rig.run_realtime(0.25)
        except Exception as e:  # noqa: BLE001 - reported, never hidden
            self._error = f"{e}\n{traceback.format_exc()}"
            self._alerter.alert(
                "problem", f"{self.spec.name} capture stopped", f"{e}. Restart the capture program"
            )

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(self.STOP_TIMEOUT_S)
            if self._thread.is_alive():
                raise RuntimeError(f"runner {self.spec.name} did not stop")
        if self.machine.status().state != MachineState.SHUT_DOWN:
            self.machine.shutdown()

    def _apply(self, job: _NewReelJob) -> None:
        """On the runner thread, which alone steps the rig: the machine opens the new reel and
        the fresh film is threaded with no step in between, so a switch of the old film cannot
        open the new reel."""
        try:
            self.machine.new_reel(job.meta)
            self.rig.load_film(self._film(self.rig.clock.now_ns()))
        except Exception as e:  # noqa: BLE001 - handed to the caller of new_reel, who raises it
            job.error = e
        finally:
            job.done.set()

    def new_reel(self, meta: ReelMeta) -> None:
        """Demo Mode: open a new reel and thread a fresh simulated film. Returns once the runner
        thread has done both (within 0.25 s); the machine's refusal is raised here."""
        if not self.alive:
            raise RuntimeError("runner is not running")
        job = _NewReelJob(meta)
        with self._pending_lock:
            if self._pending_job is not None:
                raise RuntimeError("a New Reel is already being applied")
            self._pending_job = job
        while not job.done.wait(0.05):
            if not self.alive:
                raise RuntimeError("runner stopped before the New Reel was applied")
        if job.error is not None:
            raise job.error

    @property
    def alive(self) -> bool:
        return self._thread.is_alive()

    @property
    def error(self) -> str | None:
        return self._error
