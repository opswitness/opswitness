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


def build_coverage(
    observed_jobs: set[str],
    schedules: list[dict[str, Any]] | None,
    error: str | None = None,
) -> dict[str, Any]:
    """Structured coverage verdict. A schedules file that covers one job must never
    paint an otherwise uncovered fleet green."""
    covered = sorted({str(s["job"]) for s in (schedules or []) if s.get("job")})
    uncovered = sorted(observed_jobs - set(covered))
    if error:
        status = "none"
    elif not covered:
        status = "none"
    elif uncovered:
        status = "partial"
    else:
        status = "full"
    return {
        "status": status,
        "covered_jobs": covered,
        "observed_uncovered": uncovered,
        "error": error,
    }


def build_digest(
    events: list[dict[str, Any]],
    now: datetime,
    hours: int = 24,
    missed: list[dict[str, Any]] | None = None,
    schedules: list[dict[str, Any]] | None = None,
    coverage_error: str | None = None,
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
    coverage = build_coverage({run["job"] for run in runs}, schedules, coverage_error)
    healthy = coverage["status"] == "full" and not problems and not missed
    return {
        "window_hours": hours,
        "generated_at": now.isoformat(),
        "jobs": jobs,
        "total_runs": len(runs),
        "problems": problems,
        "missed": missed,
        "coverage": coverage,
        "projection_backlog": len(pending_events(events)),
        "healthy": healthy,
    }


def _job_state(s: dict[str, int]) -> str:
    """Three-state: problem / running (neutral, NOT success) / ok."""
    if s["total"] != s["succeeded"] + s["running"] or s["degraded"]:
        return "problem"
    if s["running"]:
        return "running"
    return "ok"


_STATE_MARK = {"ok": "✅", "running": "🔄", "problem": "❌"}


def _job_line(job: str, s: dict[str, int]) -> str:
    mark = _STATE_MARK[_job_state(s)]
    parts = [f"成 {s['succeeded']}"]
    for key, zh in (("failed", "败"), ("killed", "杀"), ("spawn_failed", "起失败"),
                    ("unknown", "未知"), ("running", "跑")):
        if s[key]:
            parts.append(f"{zh} {s[key]}")
    extra = f" ⚠️degraded×{s['degraded']}" if s["degraded"] else ""
    return f"- {mark} `{job}`: {s['total']} 次（{' / '.join(parts)}）{extra}"


_COVERAGE_ZH = {"full": "完整", "partial": "部分", "none": "无"}


def render_markdown(d: dict[str, Any]) -> str:
    verdict = "🟢 健康" if d["healthy"] else "🔴 需关注"
    cov = d["coverage"]
    lines = [
        f"# 舰队日报（近 {d['window_hours']}h）— {verdict}",
        "",
        f"总运行 {d['total_runs']} 次 · 问题 {len(d['problems'])} 个 · "
        f"投影积压 {d['projection_backlog']} · watchdog 覆盖：{_COVERAGE_ZH[cov['status']]}",
    ]
    if cov["status"] == "full":
        lines[-1] += f" · 漏跑 {len(d['missed'])} 个"
    elif cov["status"] == "partial":
        lines += [
            "",
            "⚠️ **watchdog 覆盖不完整** — 以下任务有运行记录但未纳管（不在任何 schedule 内）：",
            *[f"- `{job}`" for job in cov["observed_uncovered"]],
        ]
    else:
        reason = cov["error"] or "无已纳管的 schedules（缺失/为空）"
        lines += ["", f"⚠️ **watchdog coverage unavailable** — {reason}；漏跑无从判定（这不是 0）"]
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
    """Telegram-flavored HTML (parse_mode=HTML): no markdown headings, <b>/<code> only.

    Dynamic fields are clipped so no single line can approach the chunk limit —
    the paragraph splitter therefore never has to cut inside an HTML tag.
    """
    import html

    def code(s: Any, limit: int = 256) -> str:
        text = str(s)
        if len(text) > limit:
            text = text[: limit - 1] + "…"
        return f"<code>{html.escape(text)}</code>"

    verdict = "🟢 健康" if d["healthy"] else "🔴 需关注"
    cov = d["coverage"]
    parts = [
        f"<b>舰队日报（近 {d['window_hours']}h）— {verdict}</b>",
        f"总运行 {d['total_runs']} · 问题 {len(d['problems'])} · 积压 {d['projection_backlog']}"
        f" · 覆盖 {_COVERAGE_ZH[cov['status']]}"
        + (f" · 漏跑 {len(d['missed'])}" if cov["status"] == "full" else ""),
    ]
    if cov["status"] == "partial":
        parts.append(
            "⚠️ <b>覆盖不完整</b> — 未纳管却有运行：\n"
            + "\n".join(code(j) for j in cov["observed_uncovered"])
        )
    elif cov["status"] == "none":
        parts.append("⚠️ <b>watchdog coverage unavailable</b>（无已纳管 schedules，漏跑无从判定）")
    job_lines = []
    for job, s in sorted(d["jobs"].items()):
        mark = _STATE_MARK[_job_state(s)]
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
