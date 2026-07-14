"""Disposable SQLite index over the ledger — rebuilt on demand, never authoritative."""

import json
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
CREATE TABLE IF NOT EXISTS artifacts (
  event_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  job TEXT NOT NULL,
  logical_name TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size INTEGER NOT NULL,
  mime TEXT NOT NULL,
  labels_json TEXT NOT NULL,
  cas_uri TEXT NOT NULL,
  registered_ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS artifacts_run_idx ON artifacts (run_id, registered_ts DESC);
CREATE TABLE IF NOT EXISTS artifact_outcomes (
  event_id TEXT PRIMARY KEY,
  artifact_event_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  verdict TEXT,
  actor TEXT,
  summary TEXT,
  ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS artifact_outcomes_artifact_idx
  ON artifact_outcomes (artifact_event_id, ts);
"""


def rebuild(
    db_path: Path,
    ledger: Ledger,
    *,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rebuild the index from the ledger. Returns {runs, pending_projection}."""
    events = ledger.read_all() if events is None else events
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            "DROP TABLE IF EXISTS runs;"
            "DROP TABLE IF EXISTS artifacts;"
            "DROP TABLE IF EXISTS artifact_outcomes;" + _SCHEMA
        )
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
            elif e.get("kind") == "artifact_registered":
                con.execute(
                    "INSERT INTO artifacts (event_id, run_id, job, logical_name, sha256,"
                    " size, mime, labels_json, cas_uri, registered_ts)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        e["event_id"],
                        e["run_id"],
                        p.get("job"),
                        p.get("logical_name"),
                        p.get("sha256"),
                        p.get("size"),
                        p.get("mime"),
                        json.dumps(p.get("labels", []), separators=(",", ":")),
                        p.get("cas_uri"),
                        e.get("ts"),
                    ),
                )
            elif e.get("kind") in {"artifact_eval", "artifact_signoff"}:
                con.execute(
                    "INSERT INTO artifact_outcomes (event_id, artifact_event_id, kind,"
                    " verdict, actor, summary, ts) VALUES (?,?,?,?,?,?,?)",
                    (
                        e["event_id"],
                        p.get("artifact_event_id"),
                        e["kind"],
                        p.get("verdict") or p.get("decision"),
                        p.get("evaluator") or p.get("signed_by"),
                        p.get("summary") or p.get("note"),
                        e.get("ts"),
                    ),
                )
        con.commit()
        n_runs = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        n_artifacts = con.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]
    finally:
        con.close()
    return {
        "runs": n_runs,
        "artifacts": n_artifacts,
        "pending_projection": len(pending_events(events)),
    }


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


def query_artifacts(
    db_path: Path, run_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        sql = "SELECT * FROM artifacts"
        args: list[Any] = []
        if run_id:
            sql += " WHERE run_id = ?"
            args.append(run_id)
        sql += " ORDER BY registered_ts DESC LIMIT ?"
        args.append(limit)
        return [dict(row) for row in con.execute(sql, args).fetchall()]
    finally:
        con.close()
