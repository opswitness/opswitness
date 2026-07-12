"""Disposable SQLite index over the ledger — rebuilt on demand, never authoritative."""

import sqlite3
from pathlib import Path
from typing import Any

from quarterdeck.ledger import Ledger
from quarterdeck.projector import pending_events

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  job TEXT,
  started_ts TEXT,
  finished_ts TEXT,
  status TEXT,
  exit_code INTEGER,
  duration_s REAL,
  degraded INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS runs_job_idx ON runs (job, started_ts DESC);
"""


def rebuild(db_path: Path, ledger: Ledger) -> dict[str, Any]:
    """Rebuild the index from the ledger. Returns {runs, pending_projection}."""
    events = ledger.read_all()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript("DROP TABLE IF EXISTS runs;" + _SCHEMA)
        for e in events:
            p = e.get("payload", {})
            degraded = 1 if e.get("degraded") else 0
            if e.get("kind") == "run_started":
                con.execute(
                    "INSERT OR REPLACE INTO runs (run_id, job, started_ts, status, degraded)"
                    " VALUES (?,?,?,?,?)",
                    (e["run_id"], p.get("job"), e.get("ts"), "running", degraded),
                )
            elif e.get("kind") == "run_finished":
                con.execute(
                    "INSERT INTO runs (run_id, job, finished_ts, status, exit_code,"
                    " duration_s, degraded) VALUES (?,?,?,?,?,?,?)"
                    " ON CONFLICT(run_id) DO UPDATE SET finished_ts=excluded.finished_ts,"
                    " status=excluded.status, exit_code=excluded.exit_code,"
                    " duration_s=excluded.duration_s,"
                    " degraded=MAX(runs.degraded, excluded.degraded)",
                    (
                        e["run_id"],
                        p.get("job"),
                        e.get("ts"),
                        p.get("status"),
                        p.get("exit_code"),
                        p.get("duration_s"),
                        degraded,
                    ),
                )
        con.commit()
        n_runs = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        con.close()
    return {"runs": n_runs, "pending_projection": len(pending_events(events))}


def query_runs(db_path: Path, job: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM runs"
        args: list[Any] = []
        if job:
            sql += " WHERE job = ?"
            args.append(job)
        sql += " ORDER BY COALESCE(started_ts, finished_ts) DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally:
        con.close()


def job_summary(db_path: Path) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT job, COUNT(*) AS runs,"
            " SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,"
            " MAX(COALESCE(finished_ts, started_ts)) AS last_ts,"
            " (SELECT status FROM runs r2 WHERE r2.job = runs.job"
            "   ORDER BY COALESCE(started_ts, finished_ts) DESC LIMIT 1) AS last_status"
            " FROM runs GROUP BY job ORDER BY job"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()
