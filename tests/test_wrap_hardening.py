import os
import signal
import subprocess
import sys
import time

from quarterdeck.config import Settings
from quarterdeck.ledger import Ledger
from quarterdeck.wrap.runner import run_wrapped

SK = "sk-" + "a1B2" * 8


def _settings(tmp_path, **kw) -> Settings:
    return Settings(ledger_dir=tmp_path / "ledger", **kw)


def test_started_fsync_happens_before_spawn(tmp_path, monkeypatch):
    calls: list[str] = []
    real_fsync = os.fsync
    real_popen = subprocess.Popen

    def spy_fsync(fd):
        calls.append("fsync")
        return real_fsync(fd)

    class SpyPopen(real_popen):  # type: ignore[misc,valid-type]
        def __init__(self, *args, **kwargs):
            calls.append("popen")
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("quarterdeck.ledger.os.fsync", spy_fsync)
    monkeypatch.setattr("quarterdeck.wrap.runner.subprocess.Popen", SpyPopen)
    assert run_wrapped("demo", ["true"], _settings(tmp_path)) == 0
    assert "popen" in calls and "fsync" in calls
    assert calls.index("fsync") < calls.index("popen"), calls


def test_argv_redacted_in_ledger_by_default(tmp_path):
    s = _settings(tmp_path)
    run_wrapped("demo", ["sh", "-c", "true", f"--api-key={SK}"], s)
    started = Ledger(s.ledger_dir).read_all()[0]
    recorded = " ".join(started["payload"]["argv"])
    assert SK not in recorded and "«redacted»" in recorded


def test_log_tail_redacted_and_optional(tmp_path):
    s = _settings(tmp_path)
    run_wrapped("demo", ["sh", "-c", f"echo leak {SK}"], s)
    fin = Ledger(s.ledger_dir).read_all()[-1]["payload"]
    assert SK not in fin["log_tail"] and "«redacted»" in fin["log_tail"]

    s2 = _settings(tmp_path / "b", capture_log_tail=False)
    run_wrapped("demo", ["sh", "-c", "echo visible"], s2)
    fin2 = Ledger(s2.ledger_dir).read_all()[-1]["payload"]
    assert "log_tail" not in fin2


def test_sigterm_kills_whole_process_tree(tmp_path):
    marker = "987654321"
    env = dict(os.environ, QD_LEDGER_DIR=str(tmp_path / "ledger"))
    wrapper = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "quarterdeck.cli",
            "wrap",
            "--job",
            "tree-demo",
            "--",
            "sh",
            "-c",
            f"sleep {marker} & wait",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for the grandchild sleep to exist.
    deadline = time.time() + 10
    while time.time() < deadline:
        if subprocess.run(["pgrep", "-f", f"sleep {marker}"], capture_output=True).returncode == 0:
            break
        time.sleep(0.1)
    else:
        wrapper.kill()
        raise AssertionError("grandchild never appeared")

    wrapper.send_signal(signal.SIGTERM)
    wrapper.wait(timeout=10)

    deadline = time.time() + 5
    while time.time() < deadline:
        if subprocess.run(["pgrep", "-f", f"sleep {marker}"], capture_output=True).returncode != 0:
            break
        time.sleep(0.2)
    else:
        subprocess.run(["pkill", "-f", f"sleep {marker}"])
        raise AssertionError("grandchild survived SIGTERM — process tree not reaped")
