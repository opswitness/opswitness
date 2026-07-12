"""qd digest — the daily fleet report, generated from evidence, not self-reports.

Philosophy: agents/jobs don't get to claim what they did. The digest is a pure
aggregation of the authoritative ledger (runs, failures, degradations), the watchdog
verdict, and the projection backlog. An optional LLM narrative layer can sit on top
later; the numbers never come from a model.
"""

from datetime import datetime, timedelta
from typing import Any

from quarterdeck.projector import pending_events


def build_digest(
    events: list[dict[str, Any]],
    now: datetime,
    hours: int = 24,
    missed: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cutoff = now - timedelta(hours=hours)
    runs: dict[str, dict[str, Any]] = {}
    for e in events:
        kind = e.get("kind")
        if kind not in ("run_started", "run_finished"):
            continue
        try:
            ts = datetime.fromisoformat(e["ts"])
        except (KeyError, ValueError):
            continue
        if ts < cutoff:
            continue
        run = runs.setdefault(
            e["run_id"], {"job": e.get("payload", {}).get("job", "unknown"), "status": "running"}
        )
        if kind == "run_finished":
            p = e.get("payload", {})
            run["status"] = p.get("status", "unknown")
            run["exit_code"] = p.get("exit_code")
            run["duration_s"] = p.get("duration_s")
        if e.get("degraded"):
            run["degraded"] = True

    jobs: dict[str, dict[str, int]] = {}
    for run in runs.values():
        j = jobs.setdefault(
            run["job"],
            {"total": 0, "succeeded": 0, "failed": 0, "killed": 0, "running": 0, "degraded": 0},
        )
        j["total"] += 1
        j[run["status"]] = j.get(run["status"], 0) + 1
        if run.get("degraded"):
            j["degraded"] += 1

    problems = [
        {"job": run["job"], "status": run["status"], "exit_code": run.get("exit_code")}
        for run in runs.values()
        if run["status"] in ("failed", "killed", "spawn_failed")
    ]
    return {
        "window_hours": hours,
        "generated_at": now.isoformat(),
        "jobs": jobs,
        "total_runs": len(runs),
        "problems": problems,
        "missed": missed or [],
        "projection_backlog": len(pending_events(events)),
    }


def render_markdown(d: dict[str, Any]) -> str:
    lines = [
        f"# 舰队日报（近 {d['window_hours']}h）",
        "",
        f"总运行 {d['total_runs']} 次 · 问题 {len(d['problems'])} 个 · "
        f"漏跑 {len(d['missed'])} 个 · 投影积压 {d['projection_backlog']}",
        "",
        "## 各任务表现",
    ]
    for job, s in sorted(d["jobs"].items()):
        ok_all = s["failed"] == 0 and s["killed"] == 0 and s["degraded"] == 0
        mark = "✅" if ok_all else "❌"
        extra = f" ⚠️degraded×{s['degraded']}" if s["degraded"] else ""
        lines.append(
            f"- {mark} `{job}`: {s['total']} 次（成 {s['succeeded']} / 败 {s['failed']}"
            f" / 杀 {s['killed']} / 跑 {s['running']}）{extra}"
        )
    if not d["jobs"]:
        lines.append("- （窗口内无运行记录）")
    if d["problems"]:
        lines += ["", "## 今日问题"]
        for p in d["problems"]:
            lines.append(f"- `{p['job']}` {p['status']} (exit={p.get('exit_code')})")
    if d["missed"]:
        lines += ["", "## 漏跑/无覆盖（watchdog）"]
        for m in d["missed"]:
            detail = f" overdue={m.get('overdue_seconds')}s" if m.get("overdue_seconds") else ""
            lines.append(f"- `{m['job']}`: {m['reason']}{detail}")
    lines += ["", f"_evidence-based · 由账本生成 · {d['generated_at']}_"]
    return "\n".join(lines)
