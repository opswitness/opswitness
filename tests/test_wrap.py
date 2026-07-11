from quarterdeck.config import Settings
from quarterdeck.ledger import Ledger
from quarterdeck.wrap.runner import run_wrapped


def _settings(tmp_path) -> Settings:
    return Settings(ledger_dir=tmp_path / "ledger", log_tail_bytes=8192)


def test_exit_code_mirrored_and_both_events_written(tmp_path):
    s = _settings(tmp_path)
    code = run_wrapped("demo", ["sh", "-c", "echo hi; exit 7"], s)
    assert code == 7
    events = Ledger(s.ledger_dir).read_all()
    kinds = [e["kind"] for e in events]
    assert kinds == ["run_started", "run_finished"]
    fin = events[-1]["payload"]
    assert fin["exit_code"] == 7 and fin["status"] == "failed"
    assert "hi" in fin["log_tail"]
    assert events[0]["run_id"] == events[-1]["run_id"]


def test_started_written_even_when_command_cannot_spawn(tmp_path):
    s = _settings(tmp_path)
    code = run_wrapped("demo", ["/nonexistent/binary-xyz"], s)
    assert code == 127
    events = Ledger(s.ledger_dir).read_all()
    assert [e["kind"] for e in events] == ["run_started", "run_finished"]
    assert events[-1]["payload"]["status"] == "spawn_failed"


def test_ledger_failure_never_blocks_the_job(tmp_path, capsys):
    blocked = tmp_path / "ro"
    blocked.mkdir()
    blocked.chmod(0o400)
    s = Settings(ledger_dir=blocked / "ledger", log_tail_bytes=8192)
    code = run_wrapped("demo", ["sh", "-c", "exit 0"], s)
    blocked.chmod(0o700)
    assert code == 0  # the wrapped job ran and its exit code was mirrored
    err = capsys.readouterr().err
    assert "audit evidence lost" in err


def test_success_status_recorded(tmp_path):
    s = _settings(tmp_path)
    assert run_wrapped("demo", ["true"], s) == 0
    fin = Ledger(s.ledger_dir).read_all()[-1]["payload"]
    assert fin["status"] == "succeeded" and fin["exit_code"] == 0
