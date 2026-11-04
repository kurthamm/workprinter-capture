"""Command line: `python -m wpcap demo` runs a simulated reel end to end."""

from __future__ import annotations

import argparse
import getpass
import signal
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from wpcap.config import ConfigError, hash_password, load_config, new_secret, sample_config
from wpcap.machine import MachineConfig, MachineState
from wpcap.reel import ReelFolder
from wpcap.service import Service, ServiceError
from wpcap.sim.camera import is_blurred
from wpcap.sim.film import SimFilm
from wpcap.sim.rig import SimRig
from wpcap.tls import local_names, make_local_ca, make_server_cert

S = 1_000_000_000


def demo(args: argparse.Namespace) -> int:
    config = MachineConfig(
        name="Demo WorkPrinter",
        reel_root=Path(args.reels),
        delay_ms=args.delay_ms,
        gate_min_frames=20,
        gate_empty_needed=8,
    )
    film = SimFilm(frames=args.frames, start_ns=3 * S, switch_offset_ms=args.switch_offset_ms)
    rig = SimRig(config, film)
    total_s = 3 + args.frames / 8.0 + 3
    seconds_run = 0
    while seconds_run < total_s:
        if args.realtime:
            rig.run_realtime(1.0)
        else:
            rig.run_for(S)
        seconds_run += 1
        _print_status(rig)
    # shutdown() leaves SHUT_DOWN, so take the reel's end state first.
    final_state = rig.machine.status().state
    rig.machine.shutdown()
    st = rig.machine.status()
    reel = rig.machine.reel
    blurred = 0
    if reel is not None:
        for p in sorted(ReelFolder.open(reel.path).frames_dir.glob("*.png")):
            if is_blurred(np.asarray(Image.open(p))):
                blurred += 1
    print(
        f"final: {final_state} saved {st.frames_saved} failed {st.frames_failed} blurred {blurred}"
    )
    if reel is not None:
        print(f"reel: {reel.path}")
    for level, title, message in rig.alerts:
        print(f"alert [{level}] {title}: {message}")
    ok = final_state == MachineState.REEL_FINISHED and st.frames_failed == 0 and blurred == 0
    return 0 if ok else 1


def _print_status(rig: SimRig) -> None:
    st = rig.machine.status()
    print(
        f"t={rig.clock.now_ns() / S:6.1f}s {st.state:14s} saved {st.frames_saved:5d} "
        f"failed {st.frames_failed:3d} fps {st.fps:4.1f} sync {st.sync_error_ms:.3f} ms"
    )


def cmd_hash_password(args: argparse.Namespace) -> int:
    pw = args.password if args.password is not None else sys.stdin.readline().rstrip("\r\n")
    if not pw:
        print("empty password", file=sys.stderr)
        return 2
    print(hash_password(pw))
    return 0


def _ask_password() -> str:
    while True:
        a = getpass.getpass("Choose the web page password: ")
        b = getpass.getpass("Again: ")
        if a and a == b:
            return a
        print("passwords differ or empty; try again", file=sys.stderr)


def cmd_init_config(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists():
        print(f"{out} already exists; remove it first", file=sys.stderr)
        return 2
    certs = Path(args.certs)
    pw = args.password if args.password is not None else _ask_password()
    reels = Path(args.reels)
    for n in ("WorkPrinter 1", "WorkPrinter 2"):
        (reels / n).mkdir(parents=True, exist_ok=True)
    try:
        ca_crt, ca_key = make_local_ca(certs)
    except FileExistsError:
        ca_crt, ca_key = certs / "ca.crt", certs / "ca.key"
    hosts, ips = local_names()
    hosts += [h for h in args.host if h not in hosts]
    ips += [ip for ip in args.ip if ip not in ips]
    crt, key = certs / "wpcap.crt", certs / "wpcap.key"
    if not hosts:
        print("no host names for the certificate", file=sys.stderr)
        return 2
    if not crt.exists():
        make_server_cert(ca_crt, ca_key, crt, key, hosts, ips)
    text = sample_config(hash_password(pw), reels, crt, key, new_secret())
    text = text.replace('host = "0.0.0.0"', f'host = "{args.bind}"').replace(
        "port = 8443", f"port = {args.port}"
    )
    text = text.replace("sim_frames = 300", f"sim_frames = {args.sim_frames}")
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}\nCA certificate to trust on your devices: {ca_crt}")
    return 0


def cmd_gen_cert(args: argparse.Namespace) -> int:
    certs = Path(args.certs)
    ca_crt, ca_key = certs / "ca.crt", certs / "ca.key"
    if not ca_crt.exists():
        print(f"no CA at {ca_crt}; run init-config first", file=sys.stderr)
        return 2
    crt, key = certs / "wpcap.crt", certs / "wpcap.key"
    if crt.exists() or key.exists():
        if not args.replace:
            print(f"{crt} exists; pass --replace to make a new one", file=sys.stderr)
            return 2
        crt.unlink(missing_ok=True)
        key.unlink(missing_ok=True)
    hosts, ips = local_names()
    hosts += [h for h in args.host if h not in hosts]
    ips += [ip for ip in args.ip if ip not in ips]
    if not hosts:
        print("no host names for the certificate", file=sys.stderr)
        return 2
    make_server_cert(ca_crt, ca_key, crt, key, hosts, ips)
    print(f"wrote {crt} for {', '.join(hosts + ips)}")
    return 0


def stop_signals() -> tuple[signal.Signals, ...]:
    """The signals uvicorn turns into a graceful shutdown (and re-raises afterwards)."""
    sigs = (signal.SIGINT, signal.SIGTERM)
    if hasattr(signal, "SIGBREAK"):  # Windows: Ctrl+Break, the usual "stop" from a supervisor
        sigs += (signal.SIGBREAK,)
    return sigs


def absorb_reraised_stop_signals() -> None:
    for sig in stop_signals():
        signal.signal(sig, lambda signum, frame: None)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from wpcap.web.app import create_app

    try:
        config = load_config(Path(args.config))
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    for p in (config.server.cert_file, config.server.key_file):
        if not p.exists():
            print(f"certificate file not found: {p} (run: wpcap gen-cert)", file=sys.stderr)
            return 2
    service = Service(config)
    try:
        service.start()
    except ServiceError as e:
        print(f"cannot start: {e}", file=sys.stderr)
        return 2
    try:
        app = create_app(service, config)
        hosts, ips = local_names()
        for name in hosts + ips:
            print(f"page: https://{name}:{config.server.port}/")

        class Server(uvicorn.Server):
            def handle_exit(self, sig, frame):
                # Let open event streams end so graceful shutdown does not wait on them.
                app.state.shutting_down.set()
                super().handle_exit(sig, frame)

        server = Server(
            uvicorn.Config(
                app,
                host=config.server.host,
                port=config.server.port,
                ssl_certfile=str(config.server.cert_file),
                ssl_keyfile=str(config.server.key_file),
                log_level="warning",
                timeout_graceful_shutdown=5,
            )
        )
        # What happens on Ctrl+C / SIGTERM / Ctrl+Break: server.run() installs uvicorn's own
        # handlers (a second Ctrl+C forces exit), shuts down gracefully, restores the handlers
        # that were set before, then re-raises the captured signal. The handlers installed here
        # only absorb that re-raised signal so it neither raises KeyboardInterrupt nor kills
        # the process before the service is stopped.
        absorb_reraised_stop_signals()
        server.run()
    finally:
        # A Ctrl+C during a slow stop must still interrupt it, not be absorbed.
        signal.signal(signal.SIGINT, signal.default_int_handler)
        service.stop()
        print("stopped: machines shut down, reels closed", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wpcap")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo", help="scan a simulated reel")
    d.add_argument("--reels", required=True, help="folder for reel folders")
    d.add_argument("--frames", type=int, default=300)
    d.add_argument("--delay-ms", type=float, default=40.0)
    d.add_argument("--switch-offset-ms", type=float, default=0.0)
    d.add_argument("--realtime", action="store_true")
    hp = sub.add_parser(
        "hash-password", help="print the scrypt hash of a password (stdin or --password)"
    )
    hp.add_argument("--password")

    ic = sub.add_parser(
        "init-config",
        help="write a sample config with two simulated machines, a CA and a certificate",
    )
    ic.add_argument("--out", required=True)
    ic.add_argument(
        "--reels", required=True, help="folder that will hold one subfolder per machine"
    )
    ic.add_argument(
        "--certs", required=True, help="folder for ca.crt, ca.key, wpcap.crt, wpcap.key"
    )
    ic.add_argument("--password", help="(scripts only; otherwise asked on the terminal)")
    ic.add_argument("--bind", default="0.0.0.0", dest="bind")
    ic.add_argument(
        "--host", action="append", default=[], help="extra hostname for the certificate"
    )
    ic.add_argument("--ip", action="append", default=[], help="extra IP for the certificate")
    ic.add_argument("--port", type=int, default=8443)
    ic.add_argument("--sim-frames", type=int, default=300)

    gc = sub.add_parser("gen-cert", help="make a new server certificate from the existing CA")
    gc.add_argument("--certs", required=True)
    gc.add_argument("--host", action="append", default=[])
    gc.add_argument("--ip", action="append", default=[])
    gc.add_argument("--replace", action="store_true")

    sv = sub.add_parser("serve", help="run the capture service and the web page")
    sv.add_argument("--config", required=True)

    args = parser.parse_args(argv)
    return {
        "demo": demo,
        "hash-password": cmd_hash_password,
        "init-config": cmd_init_config,
        "gen-cert": cmd_gen_cert,
        "serve": cmd_serve,
    }[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
