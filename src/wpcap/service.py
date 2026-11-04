"""The Service owns everything that runs: machines on their runners, the alert bus, startup
recovery. The web app is a thin view over it."""

from __future__ import annotations

import time
from dataclasses import asdict

from wpcap.alerts import AlertBus, NtfyAlerter
from wpcap.config import AppConfig, MachineSpec
from wpcap.health import pc_health
from wpcap.machine import Machine
from wpcap.recovery import RecoveryReport, recover, repair
from wpcap.reel import ReelFolder
from wpcap.runner import Runner, SimRunner

FRAMES_PER_FOOT = {"super8": 72, "regular8": 80}
DEFAULT_FPS = 18.0


class ServiceError(Exception):
    pass


def _needs_repair(r: RecoveryReport) -> bool:
    return bool(
        r.half_written or r.journal_truncated or r.missing_final_newline or r.corrupt_frames
        or r.orphan_clicks
    )


class Service:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        forward = NtfyAlerter(config.ntfy) if config.ntfy is not None else None
        self.bus = AlertBus(forward=forward)
        self.runners: dict[str, Runner] = {}
        self.recovery_reports: list[RecoveryReport] = []
        self._started = False
        self._stopped = False

    # ---- lifecycle -------------------------------------------------------------------------

    def start(self) -> None:
        if self._started:
            raise ServiceError("service already started")
        self._started = True
        for spec in self.config.machines:
            if not spec.reel_root.is_dir():
                raise ServiceError(f"reel root for {spec.name} not found: {spec.reel_root}")
        for spec in self.config.machines:
            self._recover_reels(spec)
        for spec in self.config.machines:
            self.runners[spec.name] = self._build_runner(spec)
        try:
            for r in self.runners.values():
                r.start()
        except Exception as start_error:
            cleanup = self._stop_all(list(self.runners.values()))
            if cleanup:
                start_error.add_note("cleanup after failed start: " + "; ".join(cleanup))
            raise

    def _build_runner(self, spec: MachineSpec) -> Runner:
        if spec.kind == "sim":
            return SimRunner(spec, self.bus.for_machine(spec.name))
        raise ServiceError(f"machine {spec.name}: unknown kind {spec.kind!r}")

    def _recover_reels(self, spec: MachineSpec) -> None:
        alerter = self.bus.for_machine(spec.name)
        for path in sorted(p for p in spec.reel_root.iterdir() if p.is_dir()):
            if not (path / "journal.jsonl").exists():
                continue
            folder = ReelFolder.open(path)
            report = recover(folder)
            if _needs_repair(report):
                repair(folder, report)
                after = recover(folder)
                alerter.alert(
                    "warning",
                    f"Recovered reel {folder.name}",
                    f"{len(after.complete_frames)} frames kept, "
                    f"{len(report.half_written)} half-written removed, "
                    f"{len(report.corrupt_frames)} corrupt frames flagged, "
                    f"{len(report.orphan_clicks)} orphan clicks closed",
                )
                report = after
            self.recovery_reports.append(report)

    @staticmethod
    def _stop_all(runners: list[Runner]) -> list[str]:
        errors: list[str] = []
        for r in runners:
            try:
                r.stop()
            except Exception as e:  # noqa: BLE001 - every runner gets its chance to stop
                errors.append(f"{type(e).__name__}: {e}")
        return errors

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        errors = self._stop_all(list(self.runners.values()))
        try:
            self.bus.close()
        except Exception as e:  # noqa: BLE001 - reported together with any runner errors
            errors.append(f"{type(e).__name__}: {e}")
        if errors:
            raise ServiceError("; ".join(errors))

    # ---- access ----------------------------------------------------------------------------

    def runner(self, name: str) -> Runner:
        return self.runners[name]  # KeyError for the web layer to turn into 404

    def machine(self, name: str) -> Machine:
        return self.runners[name].machine

    def spec(self, name: str) -> MachineSpec:
        for s in self.config.machines:
            if s.name == name:
                return s
        raise KeyError(name)

    # ---- status ----------------------------------------------------------------------------

    def snapshot(self) -> dict:
        machines = []
        for spec in self.config.machines:
            r = self.runners.get(spec.name)
            if r is None:
                continue
            st = r.machine.status()
            per_foot = FRAMES_PER_FOOT[spec.film_type]
            machines.append(
                {
                    "name": spec.name,
                    "state": str(st.state),
                    "reel": st.reel_name,
                    "segment": st.segment,
                    "saved": st.frames_saved,
                    "failed": st.frames_failed,
                    "pending": st.frames_pending,
                    "clicks": st.clicks,
                    "bounces": st.bounces,
                    "fps": round(st.fps, 1),
                    "sync_error_ms": round(st.sync_error_ms, 3),
                    "free_gb": None if st.free_bytes is None else round(st.free_bytes / 1e9, 1),
                    "feet": round(st.frames_saved / per_foot, 1),
                    "length_s": round(st.frames_saved / DEFAULT_FPS, 1),
                    "delay_ms": r.machine.config.delay_ms,
                    "film_type": spec.film_type,
                    "last_fault": None if st.last_fault is None else asdict(st.last_fault),
                    "warnings": list(st.warnings),
                    "runner_alive": r.alive,
                    "runner_error": r.error,
                }
            )
        return {"t": time.time(), "pc": pc_health(), "machines": machines}
