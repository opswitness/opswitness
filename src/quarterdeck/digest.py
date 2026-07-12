"""qd digest — the daily fleet report, generated from execution evidence.

Honesty contract:
- numbers come from the ledger, never from an agent's self-report or a model;
- this is EXECUTION evidence (process ran, exit code, duration) — it does not prove
  business outcomes (data correctness, report completeness); outcome evidence
  (artifact hashes, evals, approvals) arrives with P4 and is labeled separately;
- absence of coverage is reported as absence, never as green: no schedules file
  means "watchdog coverage unavailable", not "0 missed".
"""

from datetime import datetime, timedelta
from typing import Any

from quarterdeck.projector import pending_events

TERMINAL_BAD = ("failed", "killed", "spawn_failed", "unknown")
_KNOWN_STATUSES = ("succeeded", "failed", "killed", "spawn_failed", "running")


def _collect_runs(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for e in events:
        kind = e.get("kind")
        if kind not in ("run_started", "run_finished"):
            continue
        run = runs.setdefault(
            e["run_id"],
            {"run_id": e["run_id"], "job": e.get("payload", {}).get("job", "unknown"),
             "status": "running", "started_ts": None, "finished_ts": None},
        )
        if kind == "run_started":
            run["started_ts"] = e.get("ts")
        else:
            p = e.get("payload", {})
            status = p.get("status", "unknown")
            run["status"] = status if status in _KNOWN_STATUSES else "unknown"
            run["exit_code"] = p.get("exit_code")
            run["duration_s"] = p.get("duration_s")
            run["finished_ts"] = e.get("ts")
        if e.get("degraded"):
            run["degraded"] = True
    return runs


def _in_window(run: dict[str, Any], cutoff: datetime) -> bool:
    """A run counts if it intersects the window: finished inside it, or still running."""
    if run["finished_ts"] is None:
        return True  # still running — always current, even if started before the window
    try:
        return datetime.fromisoformat(run["finished_ts"]) >= cutoff
    except ValueError:
        return True  # unparseable timestamp: surface it rather than hide it


def build_digest(
    events: list[dict[str, Any]],
    now: datetime,
    hours: int = 24,
    missed: list[dict[str, Any]] | None = None,
    watchdog_coverage: bool = False,
) -> dict[str, Any]:
    cutoff = now - timedelta(hours=hours)
    runs = [r for r in _collect_runs(events).values() if _in_window(r, cutoff)]

    jobs: dict[str, dict[str, int]] = {}
    for run in runs:
        j = jobs.setdefault(run["job"], {s: 0 for s in (*_KNOWN_STATUSES, "unknown")} | {"total": 0, "degraded": 0})
        j["total"] += 1
        j[run["status"]] += 1
        if run.get("degraded"):
            j["degraded"] += 1

    problems = [
        {
            "run_id": run["run_id"],
            "job": run["job"],
            "status": run["status"],
            "exit_code": run.get("exit_code"),
            "ts": run.get("finished_ts") or run.get("started_ts"),
            "duration_s": run.get("duration_s"),
        }
        for run in runs
        if run["status"] in TERMINAL_BAD or run.get("degraded")
    ]
    missed = missed or []
    healthy = watchdog_coverage and not problems and not missed
    return {
        "window_hours": hours,
        "generated_at": now.isoformat(),
        "jobs": jobs,
        "total_runs": len(runs),
        "problems": problems,
        "missed": missed,
        "watchdog_coverage": watchdog_coverage,
        "projection_backlog": len(pending_events(events)),
        "healthy": healthy,
    }


def _job_healthy(s: dict[str, int]) -> bool:
    """Healthy = every terminal state succeeded, nothing degraded. Running is neutral."""
    return s["total"] == s["succeeded"] + s["running"] and s["degraded"] == 0


def _job_line(job: str, s: dict[str, int]) -> str:
    mark = "✅" if _job_healthy(s) else "❌"
    parts = [f"成 {s['succeeded']}"]
    for key, zh in (("failed", "败"), ("killed", "杀"), ("spawn_failed", "起失败"),
                    ("unknown", "未知"), ("running", "跑")):
        if s[key]:
            parts.append(f"{zh} {s[key]}")
    extra = f" ⚠️degraded×{s['degraded']}" if s["degraded"] else ""
    return f"- {mark} `{job}`: {s['total']} 次（{' / '.join(parts)}）{extra}"


def render_markdown(d: dict[str, Any]) -> str:
    verdict = "🟢 健康" if d["healthy"] else "🔴 需关注"
    lines = [
        f"# 舰队日报（近 {d['window_hours']}h）— {verdict}",
        "",
        f"总运行 {d['total_runs']} 次 · 问题 {len(d['problems'])} 个 · "
        f"投影积压 {d['projection_backlog']}",
    ]
    if d["watchdog_coverage"]:
        lines[-1] += f" · 漏跑 {len(d['missed'])} 个"
    else:
        lines += ["", "⚠️ **watchdog coverage unavailable** — 无 schedules.yaml，漏跑无从判定（这不是 0）"]
    lines += ["", "## 各任务表现（execution evidence）"]
    for job, s in sorted(d["jobs"].items()):
        lines.append(_job_line(job, s))
    if not d["jobs"]:
        lines.append("- （窗口内无运行记录）")
    if d["problems"]:
        lines += ["", "## 今日问题（每行可溯源）"]
        for p in d["problems"]:
            dur = f" {p['duration_s']}s" if p.get("duration_s") is not None else ""
            lines.append(
                f"- `{p['job']}` {p['status']} (exit={p.get('exit_code')}) "
                f"run=`{p['run_id']}` @ {p.get('ts')}{dur}"
            )
    if d["missed"]:
        lines += ["", "## 漏跑/无覆盖（watchdog）"]
        for m in d["missed"]:
            detail = f" overdue={m.get('overdue_seconds')}s" if m.get("overdue_seconds") else ""
            lines.append(f"- `{m['job']}`: {m['reason']}{detail}")
    lines += [
        "",
        "_execution-evidence-based：证明进程行为（运行/退出码/时长），不证明业务结果；"
        f"outcome 证据（artifact hash/eval/审批）随 P4 接入 · {d['generated_at']}_",
    ]
    return "\n".join(lines)


def render_telegram_html(d: dict[str, Any]) -> str:
    """Telegram-flavored HTML (parse_mode=HTML): no markdown headings, <b>/<code> only."""
    import html

    def code(s: Any) -> str:
        return f"<code>{html.escape(str(s))}</code>"

    verdict = "🟢 健康" if d["healthy"] else "🔴 需关注"
    parts = [
        f"<b>舰队日报（近 {d['window_hours']}h）— {verdict}</b>",
        f"总运行 {d['total_runs']} · 问题 {len(d['problems'])} · 积压 {d['projection_backlog']}"
        + (f" · 漏跑 {len(d['missed'])}" if d["watchdog_coverage"] else ""),
    ]
    if not d["watchdog_coverage"]:
        parts.append("⚠️ <b>watchdog coverage unavailable</b>（无 schedules.yaml，漏跑无从判定）")
    job_lines = []
    for job, s in sorted(d["jobs"].items()):
        mark = "✅" if _job_healthy(s) else "❌"
        job_lines.append(f"{mark} {code(job)} {s['total']} 次，成 {s['succeeded']}")
    if job_lines:
        parts.append("\n".join(job_lines))
    if d["problems"]:
        parts.append(
            "<b>问题</b>\n"
            + "\n".join(
                f"{code(p['job'])} {p['status']} exit={p.get('exit_code')} run={code(p['run_id'])}"
                for p in d["problems"]
            )
        )
    if d["missed"]:
        parts.append(
            "<b>漏跑</b>\n" + "\n".join(f"{code(m['job'])}: {m['reason']}" for m in d["missed"])
        )
    parts.append("<i>execution-evidence-based · 不证明业务结果</i>")
    return "\n\n".join(parts)
