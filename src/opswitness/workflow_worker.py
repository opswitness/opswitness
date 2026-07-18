"""Detached supervisor entrypoint for one allowlisted workflow launch."""

from __future__ import annotations

import argparse
import os

from opswitness.config import Settings
from opswitness.ledger import Ledger
from opswitness.notify import alert
from opswitness.workflows import (
    WORKFLOW_SCHEMA_VERSION,
    _normalised_definition,
    definition_hash,
    load_workflows,
)
from opswitness.wrap.runner import run_wrapped


def supervise(
    workflow_id: str,
    run_id: str,
    expected_hash: str,
    lock_fd: int,
    start_fd: int,
    *,
    settings: Settings | None = None,
) -> int:
    """Verify the sealed definition, then execute it under the normal run ledger."""
    settings = settings or Settings()
    ledger = Ledger(settings.ledger_dir)
    try:
        os.fstat(lock_fd)  # keep the inherited flock alive for this function's lifetime
        if os.read(start_fd, 1) != b"\x01":
            raise ValueError("dispatch evidence was not committed; refusing to execute")
        os.close(start_fd)
        start_fd = -1
        definition = load_workflows().workflows.get(workflow_id)
        if definition is None:
            raise ValueError(f"workflow disappeared before execution: {workflow_id}")
        definition = _normalised_definition(definition)
        actual_hash = definition_hash(definition)
        if actual_hash != expected_hash:
            raise ValueError(
                f"workflow definition changed before execution: expected {expected_hash}, got {actual_hash}"
            )
        return run_wrapped(
            f"workflow:{workflow_id}",
            definition.argv,
            settings,
            run_id=run_id,
            cwd=definition.cwd,
        )
    except (OSError, ValueError) as exc:
        ledger.append(
            "workflow_launch_failed",
            run_id,
            {
                "schema_version": WORKFLOW_SCHEMA_VERSION,
                "workflow_id": workflow_id,
                "job": f"workflow:{workflow_id}",
                "reason": str(exc),
            },
            fsync=True,
            degraded=True,
        )
        alert(f"workflow launch failed: {workflow_id} run={run_id}: {exc}")
        return 2
    finally:
        for fd in (start_fd, lock_fd):
            try:
                if fd >= 0:
                    os.close(fd)
            except OSError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--definition-sha256", required=True)
    parser.add_argument("--lock-fd", type=int, required=True)
    parser.add_argument("--start-fd", type=int, required=True)
    args = parser.parse_args()
    return supervise(
        args.workflow_id,
        args.run_id,
        args.definition_sha256,
        args.lock_fd,
        args.start_fd,
    )


if __name__ == "__main__":
    raise SystemExit(main())
