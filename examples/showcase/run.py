#!/usr/bin/env python3
"""Synthetic, secret-free end-to-end showcase for the trust/evidence bridge."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quarterdeck.artifacts import evaluate_artifact, register_artifact, signoff_artifact
from quarterdeck.config import Settings
from quarterdeck.digest import build_digest, render_markdown
from quarterdeck.gate import (
    fold_gate_states,
    handle_post_tool_use,
    handle_pre_tool_use,
    record_decision,
    record_linked,
)
from quarterdeck.ledger import Ledger
from quarterdeck.paperclip import PaperclipError
from quarterdeck.projector import Projector, pending_events
from quarterdeck.wrap.runner import run_wrapped


class SyntheticPaperclip:
    def __init__(self) -> None:
        self.available = False
        self.issues: list[dict[str, Any]] = []
        self.comments: dict[str, list[dict[str, Any]]] = {}
        self.products: dict[str, list[dict[str, Any]]] = {}

    def _up(self) -> None:
        if not self.available:
            raise PaperclipError("synthetic outage")

    def list_issues(self):
        self._up()
        return self.issues

    def create_issue(self, title, description):
        self._up()
        issue = {"id": f"issue-{len(self.issues) + 1}", "title": title}
        self.issues.append(issue)
        return issue

    def list_comments(self, issue_id):
        self._up()
        return self.comments.setdefault(issue_id, [])

    def post_comment(self, issue_id, body, metadata=None):
        self._up()
        item = {"id": f"comment-{len(self.comments.setdefault(issue_id, [])) + 1}", "body": body}
        self.comments[issue_id].append(item)
        return item

    def list_work_products(self, issue_id):
        self._up()
        return self.products.setdefault(issue_id, [])

    def create_work_product(self, issue_id, payload):
        self._up()
        item = {"id": f"product-{len(self.products.setdefault(issue_id, [])) + 1}", **payload}
        self.products[issue_id].append(item)
        return item


def run_showcase(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    isolated_config = output / "config"
    isolated_config.mkdir(mode=0o700, exist_ok=True)
    os.chmod(isolated_config, 0o700)
    os.environ["QD_CONFIG_DIR"] = str(isolated_config)
    settings = Settings(ledger_dir=output / "state" / "ledger")
    ledger = Ledger(settings.ledger_dir)
    if run_wrapped("synthetic-report", [sys.executable, "-c", "pass"], settings) != 0:
        raise RuntimeError("synthetic wrapped run failed")
    events = ledger.read_all()
    run_id = next(event["run_id"] for event in events if event["kind"] == "run_started")
    report = output / "report.txt"
    report.write_text("synthetic report: no user data\n")
    artifact = register_artifact(
        ledger,
        report,
        run_id=run_id,
        logical_name="synthetic-report.txt",
        labels=["requires-signoff"],
    )
    evaluate_artifact(
        ledger,
        artifact["event_id"],
        verdict="pass",
        evaluator="synthetic-golden-test",
        summary="deterministic fixture passed",
    )
    signoff_artifact(
        ledger,
        artifact["event_id"],
        decision="approved",
        signed_by="synthetic-reviewer",
        note="approved fixture",
    )

    tool = {
        "session_id": "synthetic-session",
        "tool_use_id": "synthetic-tool",
        "tool_name": "Bash",
        "tool_input": {"command": "printf synthetic"},
        "cwd": str(output),
    }
    deferred = handle_pre_tool_use(ledger, tool, ttl_seconds=60)
    gate_state = next(reversed(fold_gate_states(ledger.read_all()).values()))
    record_linked(ledger, gate_state, "synthetic-approval")
    gate_state = fold_gate_states(ledger.read_all())[gate_state.request_id]
    record_decision(
        ledger,
        gate_state,
        {"id": "synthetic-approval", "status": "approved", "decidedByUserId": "synthetic-board"},
    )
    allowed = handle_pre_tool_use(ledger, tool, ttl_seconds=60)
    handle_post_tool_use(ledger, tool, succeeded=True)

    remote = SyntheticPaperclip()
    lease = output / "state" / "projector.lease"
    outage = Projector(ledger, remote, lease).drain()
    remote.available = True
    replay = Projector(ledger, remote, lease).drain()
    no_repost = Projector(ledger, remote, lease).drain()
    schedules = [{"job": "synthetic-report", "expected_interval_seconds": 3600}]
    digest = build_digest(ledger.read_all(), datetime.now(UTC), schedules=schedules)
    markdown = render_markdown(digest)
    (output / "digest.md").write_text(markdown + "\n")
    return {
        "run_id": run_id,
        "artifact_event_id": artifact["event_id"],
        "artifact_sha256": artifact["payload"]["sha256"],
        "gate": {
            "first": deferred["hookSpecificOutput"]["permissionDecision"],
            "second": allowed["hookSpecificOutput"]["permissionDecision"],
        },
        "outage_pending": outage["pending_after"],
        "replay_projected": replay["projected"],
        "no_repost_projected": no_repost["projected"],
        "final_pending": len(pending_events(ledger.read_all())),
        "digest_healthy": digest["healthy"],
        "output": str(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_showcase(args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
