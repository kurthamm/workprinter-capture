import subprocess
import sys


def test_demo_runs_a_reel_and_exits_zero(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "wpcap", "demo", "--reels", str(tmp_path), "--frames", "150"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "final: reel_finished saved 158 failed 0 blurred 0" in r.stdout
    assert list(tmp_path.iterdir()), "a reel folder was created"


def test_demo_wrong_delay_exits_nonzero_with_blur_count(tmp_path):
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "wpcap",
            "demo",
            "--reels",
            str(tmp_path),
            "--frames",
            "60",
            "--switch-offset-ms",
            "-20",
            "--delay-ms",
            "0",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 1
    assert "blurred" in r.stdout and "blurred 0" not in r.stdout
