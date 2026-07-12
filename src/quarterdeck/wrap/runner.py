"""qd wrap — run a job under the ledger without ever breaking it (ADR-0001 v2).

Invariants:
- run_started is fsync'd to the ledger BEFORE the child is spawned;
- argv is redacted by default; log tail is redacted and can be disabled;
- the child runs in its own session (process group) so termination signals reach
  the whole tree — `launchctl unload` kills grandchildren too;
- child stdio passes through untouched (tee) while an in-memory ring keeps the tail;
- run_finished is written with fsync before we exit;
- our exit code mirrors the child's exactly;
- any ledger failure degrades to an alert — the child always runs.
"""

import os
import select
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from typing import IO, Any

from quarterdeck.config import Settings
from quarterdeck.ids import new_ulid
from quarterdeck.ledger import Ledger
from quarterdeck.notify import alert
from quarterdeck.redact import redact_argv, redact_text


def _tee(src: IO[bytes], dst: IO[bytes], ring: deque[bytes]) -> None:
    for chunk in iter(lambda: src.read(4096), b""):
        try:
            dst.write(chunk)
            dst.flush()
        except OSError:
            pass
        ring.append(chunk)


def _ring_tail(ring: deque[bytes], limit: int) -> str:
    data = b"".join(ring)[-limit:]
    return data.decode(errors="replace")


def run_wrapped(job: str, argv: list[str], settings: Settings | None = None) -> int:
    settings = settings or Settings()
    ledger = Ledger(settings.ledger_dir)
    run_id = new_ulid()
    started_at = time.monotonic()
    degraded = False

    argv_recorded = redact_argv(argv) if settings.redact else list(argv)
    started = ledger.append(
        "run_started",
        run_id,
        {"job": job, "argv": argv_recorded, "cwd": os.getcwd(), "pid": os.getpid()},
        fsync=True,  # durable BEFORE exec — power loss must not yield a ran-but-unrecorded job
    )
    if started is None:
        degraded = True
        alert(f"audit evidence lost: could not write run_started for job={job} run={run_id}")

    ring: deque[bytes] = deque(maxlen=64)
    try:
        child = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,  # own process group: signals reach the whole tree
        )
    except OSError as exc:
        ledger.append(
            "run_finished",
            run_id,
            {"job": job, "exit_code": 127, "status": "spawn_failed", "error": str(exc)},
            fsync=True,
            degraded=degraded,
        )
        alert(f"job={job} failed to spawn: {exc}")
        return 127

    # Signal handlers only write one byte to a non-blocking self-pipe. Process
    # inspection, retries, sleeps, ledger writes, and alerts stay in normal code.
    signal_r, signal_w = os.pipe()
    os.set_blocking(signal_r, False)
    os.set_blocking(signal_w, False)

    def _forward(signum: int, _frame: Any) -> None:
        try:
            os.write(signal_w, bytes((signum,)))
        except OSError:
            pass

    old_handlers = {}
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        old_handlers[sig] = signal.signal(sig, _forward)

    threads = []
    assert child.stdout is not None and child.stderr is not None
    for src, dst in ((child.stdout, sys.stdout.buffer), (child.stderr, sys.stderr.buffer)):
        t = threading.Thread(target=_tee, args=(src, dst, ring), daemon=True)
        t.start()
        threads.append(t)

    from quarterdeck.process_tree import signal_process_tree

    exit_code: int | None = None
    try:
        while exit_code is None:
            exit_code = child.poll()
            if exit_code is not None:
                break
            readable, _, _ = select.select([signal_r], [], [], 0.1)
            if not readable:
                continue
            try:
                requested = os.read(signal_r, 64)
            except BlockingIOError:
                continue
            if not requested:
                continue
            result = signal_process_tree(child.pid, requested[0])
            if result.degraded:
                degraded = True
                payload = {
                    "schema_version": 1,
                    "job": job,
                    "requested_signal": result.requested_signal,
                    "final_signal": result.final_signal,
                    "survivors": result.survivors,
                    "errors": result.errors,
                    "pid_reused": sorted(set(result.pid_reused)),
                }
                ledger.append(
                    "tree_signal_degraded", run_id, payload, fsync=True, degraded=True
                )
                alert(
                    f"process-tree signal degraded: job={job} run={run_id} "
                    f"survivors={result.survivors} errors={result.errors}"
                )
            exit_code = child.wait()
    finally:
        os.close(signal_r)
        os.close(signal_w)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)

    assert exit_code is not None
    for t in threads:
        t.join(timeout=5)

    if exit_code == 0:
        status = "succeeded"
    elif exit_code < 0:
        status = "killed"  # died by signal; CLI re-raises the same signal after ledgering
    else:
        status = "failed"
    finish_payload: dict[str, Any] = {
        "job": job,
        "exit_code": exit_code,
        "status": status,
        "duration_s": round(time.monotonic() - started_at, 3),
    }
    if exit_code < 0:
        finish_payload["signal"] = -exit_code
    if settings.capture_log_tail:
        tail = _ring_tail(ring, settings.log_tail_bytes)
        finish_payload["log_tail"] = redact_text(tail) if settings.redact else tail

    finished = ledger.append("run_finished", run_id, finish_payload, fsync=True, degraded=degraded)
    if finished is None:
        alert(f"audit evidence lost: could not write run_finished for job={job} run={run_id}")

    return exit_code
