"""Quarterdeck MCP server — the AionUi (or any MCP client) console surface.

Deliberately thin: every tool delegates to the same functions the CLI uses, so the
conversational console and the terminal can never disagree. Read-mostly by design;
the only mutating tool is project_now (idempotent, at-least-once).

Complements — does not duplicate — Paperclip's own 35-tool MCP server: Paperclip
covers issues/projects/comments; Quarterdeck covers the external-fleet ledger,
watchdog verdicts, and projection control.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quarterdeck.config import Settings, config_dir, resolve_api_key
from quarterdeck.index import job_summary, query_runs, rebuild
from quarterdeck.ledger import Ledger
from quarterdeck.projector import pending_events


def _settings() -> Settings:
    return Settings()


def _index_db(settings: Settings) -> Path:
    return settings.ledger_dir.parent / "index.db"


def fleet_status() -> dict[str, Any]:
    settings = _settings()
    ledger = Ledger(settings.ledger_dir)
    info = rebuild(_index_db(settings), ledger)
    return {"jobs": job_summary(_index_db(settings)), **info}


def runs(job: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    settings = _settings()
    rebuild(_index_db(settings), Ledger(settings.ledger_dir))
    return query_runs(_index_db(settings), job=job, limit=limit)


def run_events(run_id: str) -> list[dict[str, Any]]:
    settings = _settings()
    return [e for e in Ledger(settings.ledger_dir).read_all() if e.get("run_id") == run_id]


def projection_backlog() -> dict[str, Any]:
    settings = _settings()
    pending = pending_events(Ledger(settings.ledger_dir).read_all())
    return {
        "pending": len(pending),
        "oldest": pending[0]["ts"] if pending else None,
        "by_job": _count_by_job(pending),
    }


def _count_by_job(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        job = e.get("payload", {}).get("job", "unknown")
        counts[job] = counts.get(job, 0) + 1
    return counts


def watchdog_verdict(schedules_file: str = "") -> dict[str, Any]:
    import yaml

    from quarterdeck.watchdog import check

    path = Path(schedules_file) if schedules_file else config_dir() / "schedules.yaml"
    if not path.exists():
        return {"error": f"no schedules file at {path}"}
    schedules = yaml.safe_load(path.read_text()).get("jobs", [])
    settings = _settings()
    missed = check(schedules, Ledger(settings.ledger_dir).read_all(), datetime.now(UTC))
    return {"scheduled": len(schedules), "missed": missed, "healthy": not missed}


def project_now() -> dict[str, Any]:
    from quarterdeck.paperclip import PaperclipClient
    from quarterdeck.projector import Projector

    settings = _settings()
    api_key = resolve_api_key(settings)
    if not api_key or not settings.paperclip.company_id:
        return {"error": "paperclip api key / company_id not configured"}
    client = PaperclipClient(settings.paperclip.api_base, api_key, settings.paperclip.company_id)
    projector = Projector(
        Ledger(settings.ledger_dir), client, settings.ledger_dir.parent / "projector.lease"
    )
    return projector.drain()


def build_server() -> Any:
    """Construct the FastMCP server (import deferred so the [mcp] extra stays optional)."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        "quarterdeck",
        instructions=(
            "Quarterdeck: run ledger, watchdog, and Paperclip projection control for an "
            "external script/agent fleet. Read tools are safe; project_now writes to "
            "Paperclip (at-least-once, idempotent via reconciliation)."
        ),
    )

    @server.tool(description="Fleet at a glance: per-job last state, run counts, projection backlog")
    def qd_fleet_status() -> str:
        return json.dumps(fleet_status(), ensure_ascii=False)

    @server.tool(description="Recent runs from the authoritative ledger (optionally filter by job)")
    def qd_runs(job: str = "", limit: int = 20) -> str:
        return json.dumps(runs(job or None, limit), ensure_ascii=False)

    @server.tool(description="Full event chain (started/finished/acks) for one run_id")
    def qd_run_events(run_id: str) -> str:
        return json.dumps(run_events(run_id), ensure_ascii=False)

    @server.tool(description="Projection backlog: events not yet mirrored into Paperclip")
    def qd_projection_backlog() -> str:
        return json.dumps(projection_backlog(), ensure_ascii=False)

    @server.tool(description="Watchdog verdict: overdue / never-run / unsupported schedules (fail-closed)")
    def qd_watchdog() -> str:
        return json.dumps(watchdog_verdict(), ensure_ascii=False)

    @server.tool(description="Drain unacked ledger events into Paperclip now (at-least-once)")
    def qd_project_now() -> str:
        return json.dumps(project_now(), ensure_ascii=False)

    return server
