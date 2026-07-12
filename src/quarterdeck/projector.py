"""Projector — drains unacked ledger events into Paperclip (ADR-0001 v3).

Semantics: at-least-once + reconciliation, single instance under an exclusive flock lease.
Commit order = ledger file order. Acks are ledger events themselves (`projection_ack`),
so the outbox stays the single source of truth and the SQLite index stays disposable.
"""

import fcntl
import os
import re
from pathlib import Path
from typing import Any

from quarterdeck.ledger import Ledger
from quarterdeck.paperclip import PaperclipClient, PaperclipError

ISSUE_TITLE_PREFIX = "[qd] "
BODY_MARKER = re.compile(r"qd:event:([0-9A-HJKMNP-TV-Z]{26})")
PROJECTED_KINDS = ("run_started", "run_finished")


def qd_metadata(event_id: str) -> dict[str, Any]:
    """The legal comment-metadata shape (strict schema: version/sourceRunId/sections)."""
    return {
        "version": 1,
        "sections": [
            {"rows": [{"type": "key_value", "label": "qd_event_id", "value": event_id}]}
        ],
    }


def extract_remote_event_ids(comments: list[dict[str, Any]]) -> set[str]:
    """Recover qd event ids from remote comments: metadata rows first, body marker fallback."""
    found: set[str] = set()
    for comment in comments:
        meta = comment.get("metadata") or {}
        for section in meta.get("sections") or []:
            for row in section.get("rows") or []:
                if row.get("label") == "qd_event_id" and isinstance(row.get("value"), str):
                    found.add(row["value"])
        body = comment.get("body") or ""
        found.update(BODY_MARKER.findall(body))
    return found


def pending_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    acked = {
        e["payload"].get("event_id")
        for e in events
        if e.get("kind") == "projection_ack"
    }
    return [
        e for e in events if e.get("kind") in PROJECTED_KINDS and e["event_id"] not in acked
    ]


def _comment_body(event: dict[str, Any]) -> str:
    p = event["payload"]
    if event["kind"] == "run_started":
        head = f"▶️ run started — `{p.get('job')}`"
        detail = f"argv: `{' '.join(p.get('argv', []))}`"
    else:
        icon = "✅" if p.get("status") == "succeeded" else "❌"
        head = f"{icon} run {p.get('status')} — `{p.get('job')}` (exit {p.get('exit_code')})"
        detail = f"duration: {p.get('duration_s')}s"
        tail = p.get("log_tail")
        if tail:
            detail += f"\n\n```\n{tail[-1500:]}\n```"
    return f"{head}\n{detail}\n\nqd:event:{event['event_id']}"


class Projector:
    def __init__(self, ledger: Ledger, client: PaperclipClient, lease_path: Path) -> None:
        self.ledger = ledger
        self.client = client
        self.lease_path = lease_path
        self._issue_cache: dict[str, str] = {}
        self._remote_ids_cache: dict[str, set[str]] = {}

    def _issue_for(self, job: str) -> str:
        if job in self._issue_cache:
            return self._issue_cache[job]
        title = ISSUE_TITLE_PREFIX + job
        for issue in self.client.list_issues():
            if issue.get("title") == title:
                self._issue_cache[job] = issue["id"]
                return issue["id"]
        created = self.client.create_issue(
            title,
            f"External job `{job}` wrapped by Quarterdeck. "
            f"Runs are recorded in the local authoritative ledger; comments here are "
            f"projections (at-least-once).",
        )
        self._issue_cache[job] = created["id"]
        return created["id"]

    def _remote_event_ids(self, issue_id: str) -> set[str]:
        if issue_id not in self._remote_ids_cache:
            self._remote_ids_cache[issue_id] = extract_remote_event_ids(
                self.client.list_comments(issue_id)
            )
        return self._remote_ids_cache[issue_id]

    def drain(self) -> dict[str, int]:
        """Project all unacked events in commit order. Returns counters."""
        stats = {"projected": 0, "reconciled": 0, "skipped_errors": 0, "pending_after": 0}
        self.lease_path.parent.mkdir(parents=True, exist_ok=True)
        lease_fd = os.open(self.lease_path, os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            try:
                fcntl.flock(lease_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                stats["skipped_errors"] += 1
                return stats

            events = self.ledger.read_all()
            for event in pending_events(events):
                job = event["payload"].get("job", "unknown")
                try:
                    issue_id = self._issue_for(job)
                    if event["event_id"] in self._remote_event_ids(issue_id):
                        # Crash window: posted previously but ack was lost. Heal without repost.
                        self._ack(event, "comment", "reconciled")
                        stats["reconciled"] += 1
                        continue
                    created = self.client.post_comment(
                        issue_id, _comment_body(event), qd_metadata(event["event_id"])
                    )
                    self._remote_ids_cache[issue_id].add(event["event_id"])
                    self._ack(event, "comment", str(created.get("id", "")))
                    stats["projected"] += 1
                except PaperclipError:
                    stats["skipped_errors"] += 1
                    # Leave unacked: replayed on next drain.
            stats["pending_after"] = len(pending_events(self.ledger.read_all()))
            return stats
        finally:
            os.close(lease_fd)

    def _ack(self, event: dict[str, Any], remote_kind: str, remote_id: str) -> None:
        self.ledger.append(
            "projection_ack",
            event["run_id"],
            {"event_id": event["event_id"], "remote_kind": remote_kind, "remote_id": remote_id},
        )
