import os
import signal
import subprocess
import sys
import time

import psutil

from quarterdeck.config import Settings
from quarterdeck.ledger import Ledger
from quarterdeck.process_tree import ProcessIdentity, signal_process_tree
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


def test_child_killed_by_signal_recorded_as_killed(tmp_path):
    s = _settings(tmp_path)
    code = run_wrapped("demo", ["sh", "-c", "kill -TERM $$"], s)
    assert code == -signal.SIGTERM  # raw wait() semantics preserved by the library layer
    fin = Ledger(s.ledger_dir).read_all()[-1]["payload"]
    assert fin["status"] == "killed" and fin["signal"] == signal.SIGTERM


def test_sigterm_kills_whole_process_tree(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
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
            f"sleep 999 & echo $! > {pid_file}; wait",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # The child publishes the exact grandchild PID; no process-list oracle needed.
    deadline = time.time() + 10
    while time.time() < deadline:
        if pid_file.exists() and pid_file.read_text().strip():
            break
        time.sleep(0.1)
    else:
        wrapper.kill()
        raise AssertionError("grandchild never appeared")

    grandchild_pid = int(pid_file.read_text())
    grandchild_created = psutil.Process(grandchild_pid).create_time()
    wrapper.send_signal(signal.SIGTERM)
    wrapper.wait(timeout=10)
    # Exit semantics mirror the death: the wrapper itself dies by SIGTERM,
    # not by a synthetic positive exit code.
    assert wrapper.returncode == -signal.SIGTERM, wrapper.returncode

    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            process = psutil.Process(grandchild_pid)
            gone = (
                abs(process.create_time() - grandchild_created) > 0.001
                or not process.is_running()
                or process.status() == psutil.STATUS_ZOMBIE
            )
        except psutil.NoSuchProcess:
            gone = True
        if gone:
            break
        time.sleep(0.2)
    else:
        try:
            psutil.Process(grandchild_pid).kill()
        except psutil.NoSuchProcess:
            pass
        raise AssertionError("grandchild survived SIGTERM — process tree not reaped")


class FakeInspector:
    def __init__(self, *, survive_term=True, permission_denied=False, reused=False):
        self.identities = [ProcessIdentity(100, 1.0, 0), ProcessIdentity(101, 2.0, 1)]
        self.alive_pids = {100, 101}
        self.survive_term = survive_term
        self.permission_denied = permission_denied
        self.reused = reused
        self.sent: list[tuple[int, int]] = []

    def snapshot(self, root_pid):
        assert root_pid == 100
        return self.identities

    def alive(self, identity):
        return identity.pid in self.alive_pids

    def send(self, identity, signum):
        self.sent.append((identity.pid, signum))
        if self.reused and identity.pid == 101:
            self.alive_pids.remove(101)
            raise ProcessLookupError("pid reused")
        if self.permission_denied:
            raise PermissionError("MDM denied")
        if signum == signal.SIGKILL or not self.survive_term:
            self.alive_pids.discard(identity.pid)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_process_tree_success_leaf_first():
    inspector = FakeInspector(survive_term=False)
    clock = FakeClock()
    result = signal_process_tree(
        100,
        signal.SIGTERM,
        inspector=inspector,
        clock=clock,
        sleeper=clock.sleep,
        group_signal=lambda _pid, _sig: None,
    )
    assert result.degraded is False and result.survivors == []
    assert inspector.sent[:2] == [(101, signal.SIGTERM), (100, signal.SIGTERM)]


def test_process_tree_escalates_to_sigkill_within_budget():
    inspector = FakeInspector(survive_term=True)
    clock = FakeClock()
    result = signal_process_tree(
        100,
        signal.SIGTERM,
        inspector=inspector,
        clock=clock,
        sleeper=clock.sleep,
        group_signal=lambda _pid, _sig: None,
    )
    assert result.degraded is False and result.final_signal == signal.SIGKILL
    assert (101, signal.SIGKILL) in inspector.sent and clock.now <= 1.0


def test_process_tree_permission_denial_is_degraded_and_bounded():
    inspector = FakeInspector(permission_denied=True)
    clock = FakeClock()

    def denied(_pid, _sig):
        raise PermissionError("killpg denied")

    result = signal_process_tree(
        100,
        signal.SIGTERM,
        inspector=inspector,
        clock=clock,
        sleeper=clock.sleep,
        group_signal=denied,
    )
    assert result.degraded is True and result.survivors == [100, 101]
    assert any("PermissionError" in error for error in result.errors)
    assert clock.now <= 1.0


def test_process_tree_pid_reuse_is_never_signalled_as_new_process():
    inspector = FakeInspector(survive_term=False, reused=True)
    clock = FakeClock()
    result = signal_process_tree(
        100,
        signal.SIGTERM,
        inspector=inspector,
        clock=clock,
        sleeper=clock.sleep,
        group_signal=lambda _pid, _sig: None,
    )
    assert 101 in result.pid_reused and 101 not in result.survivors
