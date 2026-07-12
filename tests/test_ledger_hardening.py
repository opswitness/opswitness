import stat
import subprocess
import sys

from quarterdeck.ledger import Ledger


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_dir_and_file_permissions(tmp_path):
    led = Ledger(tmp_path / "ledger")
    led.append("run_started", "01P", {"job": "demo"})
    root = tmp_path / "ledger"
    assert _mode(root) == 0o700
    jsonl = next(root.glob("*.jsonl"))
    assert _mode(jsonl) == 0o600


def test_preexisting_lax_file_permissions_are_tightened(tmp_path):
    led = Ledger(tmp_path / "ledger")
    led.append("tick", "01Q", {})
    jsonl = next((tmp_path / "ledger").glob("*.jsonl"))
    jsonl.chmod(0o644)  # simulate a file created before the policy
    led.append("tick", "01Q", {})
    assert _mode(jsonl) == 0o600


def test_torn_line_quarantined_exactly_once(tmp_path):
    led = Ledger(tmp_path)
    led.append("tick", "01R", {})
    path = next(tmp_path.glob("*.jsonl"))
    with open(path, "ab") as f:
        f.write(b'{"broken":')
    led.read_events(path)
    led.read_events(path)  # second read must not duplicate the quarantine entry
    torn = path.with_suffix(path.suffix + ".torn")
    assert torn.read_text().count('{"broken":') == 1


def test_multiprocess_concurrent_append(tmp_path):
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from quarterdeck.ledger import Ledger\n"
        "led = Ledger(Path(sys.argv[1]))\n"
        "for i in range(30):\n"
        "    assert led.append('tick', f'p{sys.argv[2]}-{i}', {'i': i}) is not None\n"
    )
    procs = [
        subprocess.Popen([sys.executable, "-c", script, str(tmp_path), str(n)])
        for n in range(4)
    ]
    assert all(p.wait() == 0 for p in procs)
    led = Ledger(tmp_path)
    events = led.read_all()
    assert len(events) == 120  # no interleaved/merged lines
    assert not list(tmp_path.glob("*.torn"))  # every line parsed cleanly
    assert len({e["event_id"] for e in events}) == 120
