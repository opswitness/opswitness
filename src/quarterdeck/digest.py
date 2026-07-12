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
    retired: list[str] | None = None,
    extra_disabled: list[str] | None = None,
    observed_window: set[str] | None = None,
) -> dict[str, Any]:
    """Structured coverage verdict.

    Rules (review-hardened, twice):
    - only ACTIVE schedules count as covering (enabled, interval-supported);
      a disabled or calendar/unsupported entry is registered, not covered;
    - the coverage universe is EVERY job the ledger has ever seen — the report
      window scopes performance stats, never the universe (a stray that ran
      48h ago is still a stray today);
    - the only audited way to excuse a known job is `retired:` in the user config.
    """
    retired_set = {str(r) for r in (retired or [])}
    window = observed_window if observed_window is not None else observed_jobs
    active: set[str] = set()
    disabled: set[str] = {str(j) for j in (extra_disabled or [])}
    unsupported: set[str] = set()
    for s in schedules or []:
        job = s.get("job")
        if not job:
            continue
        job = str(job)
        if s.get("enabled", True) is False:
            disabled.add(job)
        elif s.get("expected_interval_seconds") is None:
            unsupported.add(job)
        else:
            active.add(job)

    # Retirement excuses only jobs that are actually gone. A retired job running in
    # the current window means the retirement is stale — it must resurface.
    retired_but_active = sorted((retired_set & window) - active)
    effective_retired = retired_set - set(retired_but_active)

    not_covered = observed_jobs - active - effective_retired
    observed_disabled = sorted(not_covered & disabled)
    observed_unsupported = sorted(not_covered & unsupported)
    observed_unregistered = sorted(
        not_covered - disabled - unsupported - set(retired_but_active)
    )

    if error or not active:
        status = "none"
    elif not_covered:
        status = "partial"
    else:
        status = "full"
    return {
        "status": status,
        "active_covered": sorted(active),
        "disabled": sorted(disabled),
        "unsupported": sorted(unsupported),
        "retired": sorted(retired_set),
        "retired_but_active": retired_but_active,
        "observed_unregistered": observed_unregistered,
        "observed_disabled": observed_disabled,
        "observed_unsupported": observed_unsupported,
        "error": error,
    }


def build_digest(
    events: list[dict[str, Any]],
    now: datetime,
    hours: int = 24,
    missed: list[dict[str, Any]] | None = None,
    schedules: list[dict[str, Any]] | None = None,
    coverage_error: str | None = None,
    retired: list[str] | None = None,
    extra_disabled: list[str] | None = None,
) -> dict[str, Any]:
    cutoff = now - timedelta(hours=hours)
    all_runs = _collect_runs(events)
    runs = [r for r in all_runs.values() if _in_window(r, cutoff)]
    # Coverage universe: every job the ledger has EVER seen, not just this window.
    observed_all = {r["job"] for r in all_runs.values()}

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
    coverage = build_coverage(
        observed_all,
        schedules,
        coverage_error,
        retired=retired,
        extra_disabled=extra_disabled,
        observed_window={run["job"] for run in runs},
    )
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
    lines[-1] += (
        f"（活跃 {len(cov['active_covered'])} · 停用 {len(cov['disabled'])} · "
        f"不支持 {len(cov['unsupported'])} · 退役 {len(cov['retired'])}）"
    )
    def _gap_lines(c: dict[str, Any]) -> list[str]:
        out = [f"- `{job}`（未登记）" for job in c["observed_unregistered"]]
        out += [f"- `{job}`（已登记但停用）" for job in c["observed_disabled"]]
        out += [f"- `{job}`（已登记但 watchdog 不支持）" for job in c["observed_unsupported"]]
        out += [f"- `{job}`（已退役却仍在运行——退役已过期）" for job in c["retired_but_active"]]
        return out

    if cov["status"] == "full":
        lines[-1] += f" · 漏跑 {len(d['missed'])} 个"
    elif cov["status"] == "partial":
        lines += ["", "⚠️ **watchdog 覆盖不完整** — 账本已知但无活跃监控的任务："]
        lines += _gap_lines(cov)
    else:
        reason = cov["error"] or "无活跃监控的 schedules（缺失/为空/全部停用或不支持）"
        lines += ["", f"⚠️ **watchdog coverage unavailable** — {reason}；漏跑无从判定（这不是 0）"]
        gaps = _gap_lines(cov)
        if gaps:
            lines += ["", "账本已知、当前无任何监控的任务："] + gaps
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
    gaps = (
        cov["observed_unregistered"]
        + cov["observed_disabled"]
        + cov["observed_unsupported"]
        + cov["retired_but_active"]
    )
    if cov["status"] == "partial":
        parts.append(
            "⚠️ <b>覆盖不完整</b> — 账本已知但无活跃监控：\n" + "\n".join(code(j) for j in gaps)
        )
    elif cov["status"] == "none":
        note = "⚠️ <b>watchdog coverage unavailable</b>（无活跃监控的 schedules，漏跑无从判定）"
        if gaps:
            note += "\n已知无监控任务：\n" + "\n".join(code(j) for j in gaps)
        parts.append(note)
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
