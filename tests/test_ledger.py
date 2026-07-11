import json

from quarterdeck.ledger import Ledger


def test_append_and_read_roundtrip(tmp_path):
    led = Ledger(tmp_path)
    e1 = led.append("run_started", "01TEST", {"job": "demo"})
    e2 = led.append("run_finished", "01TEST", {"exit_code": 0}, fsync=True)
    assert e1 and e2 and e1["event_id"] != e2["event_id"]
    events = led.read_all()
    assert [e["kind"] for e in events] == ["run_started", "run_finished"]


def test_torn_tail_is_healed_and_quarantined(tmp_path):
    led = Ledger(tmp_path)
    led.append("run_started", "01A", {"job": "demo"})
    path = next(tmp_path.glob("*.jsonl"))
    with open(path, "ab") as f:  # simulate a crash mid-write: partial line, no newline
        f.write(b'{"event_id":"01TORN","kind":"run_fin')
    e = led.append("run_finished", "01A", {"exit_code": 0})  # must heal, not merge
    assert e is not None
    events = led.read_events(path)
    assert [ev["kind"] for ev in events] == ["run_started", "run_finished"]
    torn = path.with_suffix(path.suffix + ".torn")
    assert torn.exists() and "01TORN" in torn.read_text()


def test_append_failure_returns_none_not_raise(tmp_path):
    blocked = tmp_path / "noperm"
    blocked.mkdir()
    blocked.chmod(0o400)  # not writable, not traversable for subdir creation
    led = Ledger(blocked / "ledger")
    assert led.append("run_started", "01B", {"job": "demo"}) is None
    blocked.chmod(0o700)


def test_events_are_single_lines_lexically_ordered(tmp_path):
    led = Ledger(tmp_path)
    for i in range(5):
        led.append("tick", f"01C{i}", {"i": i})
    path = next(tmp_path.glob("*.jsonl"))
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 5
    ids = [json.loads(line)["event_id"] for line in lines]
    assert ids == sorted(ids)  # ULID lexicographic == creation order
