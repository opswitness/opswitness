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

from opswitness.lifecycle import lifecycle_sets
from opswitness.projector import pending_events
from opswitness.schedules import schedules_by_state

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


def _event_in_window(event: dict[str, Any], cutoff: datetime) -> bool:
    try:
        return datetime.fromisoformat(str(event.get("ts"))) >= cutoff
    except (TypeError, ValueError):
        return True


def _collect_outcomes(events: list[dict[str, Any]], cutoff: datetime) -> dict[str, Any]:
    registrations = {
        event["event_id"]: event
        for event in events
        if event.get("kind") == "artifact_registered"
    }
    evals: dict[str, dict[str, Any]] = {}
    signoffs: dict[str, dict[str, Any]] = {}
    touched = {
        event_id for event_id, event in registrations.items() if _event_in_window(event, cutoff)
    }
    for event in events:
        payload = event.get("payload", {})
        artifact_id = payload.get("artifact_event_id")
        if not isinstance(artifact_id, str) or artifact_id not in registrations:
            continue
        if event.get("kind") == "artifact_eval":
            evals[artifact_id] = event
        elif event.get("kind") == "artifact_signoff":
            signoffs[artifact_id] = event
        else:
            continue
        if _event_in_window(event, cutoff):
            touched.add(artifact_id)
    items: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    pending_required = 0
    for artifact_id in sorted(touched):
        event = registrations[artifact_id]
        payload = event["payload"]
        evaluation = evals.get(artifact_id, {}).get("payload", {})
        signoff = signoffs.get(artifact_id, {}).get("payload", {})
        requires_signoff = "requires-signoff" in payload.get("labels", [])
        pending = requires_signoff and not signoff
        item = {
            "event_id": artifact_id,
            "run_id": event.get("run_id"),
            "job": payload.get("job"),
            "logical_name": payload.get("logical_name"),
            "sha256": payload.get("sha256"),
            "size": payload.get("size"),
            "eval": evaluation.get("verdict"),
            "signoff": signoff.get("decision"),
            "requires_signoff": requires_signoff,
            "pending_signoff": pending,
        }
        items.append(item)
        if pending:
            pending_required += 1
        if evaluation.get("verdict") == "fail" or signoff.get("decision") == "changes_requested":
            problems.append(item)
    return {
        "items": items,
        "registered": len(items),
        "eval_pass": sum(item["eval"] == "pass" for item in items),
        "eval_fail": sum(item["eval"] == "fail" for item in items),
        "approved": sum(item["signoff"] == "approved" for item in items),
        "changes_requested": sum(item["signoff"] == "changes_requested" for item in items),
        "pending_required": pending_required,
        "problems": problems,
    }


def build_coverage(
    observed_jobs: set[str],
    schedules: list[dict[str, Any]] | None,
    error: str | None = None,
    events: list[dict[str, Any]] | None = None,
    on_demand_jobs: set[str] | None = None,
) -> dict[str, Any]:
    """Structured coverage verdict.

    Rules (review-hardened, twice):
    - only ACTIVE schedules count as covering (enabled, interval-supported);
      a disabled or calendar/unsupported entry is registered, not covered;
    - the coverage universe is EVERY job the ledger has ever seen — the report
      window scopes performance stats, never the universe (a stray that ran
      48h ago is still a stray today);
    - a run tied by run_id to a durable workflow_launch_requested event is explicitly
      on-demand, not a missing schedule; its execution result still affects health;
    - retirement is excused only by append-only job lifecycle events; a subsequent
      run resurrects the job and breaks coverage until an explicit unretire.
    """
    grouped = schedules_by_state(schedules or [])
    active = set(grouped["active"])
    disabled = set(grouped["disabled"])
    unsupported = set(grouped["unsupported"])
    retired_set, resurrected_set = lifecycle_sets(events or [])
    resurrected = resurrected_set & observed_jobs

    not_covered = (observed_jobs - active - retired_set) | resurrected
    observed_disabled = sorted(not_covered & disabled)
    observed_unsupported = sorted(not_covered & unsupported)
    observed_unregistered = sorted(
        not_covered - disabled - unsupported - resurrected
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
        "resurrected": sorted(resurrected),
        "observed_unregistered": observed_unregistered,
        "observed_disabled": observed_disabled,
        "observed_unsupported": observed_unsupported,
        "on_demand": sorted(on_demand_jobs or set()),
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
    all_runs = _collect_runs(events)
    runs = [r for r in all_runs.values() if _in_window(r, cutoff)]
    # Coverage universe: every scheduled/external job the ledger has EVER seen, not just
    # this window. A durable workflow request marks its matching run_id as intentionally
    # on-demand; it remains in performance/health, but is not a missing schedule.
    on_demand_run_ids = {
        str(event.get("run_id"))
        for event in events
        if event.get("kind") == "workflow_launch_requested"
    }
    on_demand_jobs = {
        run["job"] for run_id, run in all_runs.items() if run_id in on_demand_run_ids
    }
    observed_all = {
        run["job"] for run_id, run in all_runs.items() if run_id not in on_demand_run_ids
    }

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
        events=events,
        on_demand_jobs=on_demand_jobs,
    )
    outcomes = _collect_outcomes(events, cutoff)
    healthy = (
        coverage["status"] == "full"
        and not problems
        and not missed
        and not outcomes["problems"]
        and outcomes["pending_required"] == 0
    )
    return {
        "window_hours": hours,
        "generated_at": now.isoformat(),
        "jobs": jobs,
        "total_runs": len(runs),
        "problems": problems,
        "missed": missed,
        "coverage": coverage,
        "projection_backlog": len(pending_events(events)),
        "outcomes": outcomes,
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
        f"不支持 {len(cov['unsupported'])} · 退役 {len(cov['retired'])} · "
        f"按需 {len(cov['on_demand'])}）"
    )
    def _gap_lines(c: dict[str, Any]) -> list[str]:
        out = [f"- `{job}`（未登记）" for job in c["observed_unregistered"]]
        out += [f"- `{job}`（已登记但停用）" for job in c["observed_disabled"]]
        out += [f"- `{job}`（已登记但 watchdog 不支持）" for job in c["observed_unsupported"]]
        out += [f"- `{job}`（退休后再次运行——必须显式 unretire）" for job in c["resurrected"]]
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
    outcomes = d["outcomes"]
    lines += ["", "## 业务结果证据（outcome evidence）"]
    if not outcomes["items"]:
        lines.append("- （窗口内无 artifact/eval/signoff 事件）")
    else:
        lines.append(
            f"- artifact {outcomes['registered']} · eval 通过 {outcomes['eval_pass']} / "
            f"失败 {outcomes['eval_fail']} · 审签通过 {outcomes['approved']} / "
            f"退回 {outcomes['changes_requested']} · 必签待审 {outcomes['pending_required']}"
        )
        for item in outcomes["items"]:
            state = (
                "❌"
                if item in outcomes["problems"]
                else "⏳"
                if item["pending_signoff"]
                else "✅"
            )
            lines.append(
                f"- {state} `{item['logical_name']}` sha256=`{str(item['sha256'])[:12]}` "
                f"eval={item['eval'] or '-'} signoff={item['signoff'] or '-'} "
                f"artifact=`{item['event_id']}`"
            )
    lines += [
        "",
        "_execution-evidence-based：execution evidence 证明进程行为；"
        "outcome evidence 来自 artifact hash/eval/审签。"
        f"两者互不替代 · {d['generated_at']}_",
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
        f" · 按需 {len(cov['on_demand'])}"
        + (f" · 漏跑 {len(d['missed'])}" if cov["status"] == "full" else ""),
    ]
    gaps = (
        cov["observed_unregistered"]
        + cov["observed_disabled"]
        + cov["observed_unsupported"]
        + cov["resurrected"]
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
    outcomes = d["outcomes"]
    if outcomes["items"]:
        parts.append(
            "<b>业务结果证据</b>\n"
            f"artifact {outcomes['registered']} · eval失败 {outcomes['eval_fail']} · "
            f"审签退回 {outcomes['changes_requested']} · 必签待审 {outcomes['pending_required']}"
        )
    parts.append("<i>execution evidence 与 outcome evidence 分开计算</i>")
    return "\n\n".join(parts)


def render_page_html(d: dict[str, Any]) -> str:
    """Self-contained static HTML report — a file, not a service.

    Doctrine: the platform layer never runs its own web UI; it may EMIT a web-openable
    evidence report (no server, no state, no interaction). Inline CSS only, every
    dynamic field escaped, light/dark via prefers-color-scheme, Telegram-attachable.
    """
    import html as _html

    def esc(value: Any) -> str:
        return _html.escape(str(value))

    cov = d["coverage"]
    outcomes = d["outcomes"]
    verdict_ok = bool(d["healthy"])
    verdict_text = "🟢 健康" if verdict_ok else "🔴 需关注"
    verdict_class = "ok" if verdict_ok else "bad"

    head = (
        "<!doctype html><html lang=\"zh\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>舰队日报 · {esc(d['generated_at'][:10])}</title><style>"
        ":root{color-scheme:light dark;--fg:#1c1c1a;--muted:#5f5e5a;--bg:#fdfcf9;"
        "--line:#d9d7cf;--card:#f4f2ec;--ok:#0f6e56;--bad:#a32d2d;--warn:#854f0b}"
        "@media(prefers-color-scheme:dark){:root{--fg:#e8e6df;--muted:#a3a29b;"
        "--bg:#1b1b19;--line:#3a3936;--card:#242422;--ok:#5dcaa5;--bad:#f09595;--warn:#fac775}}"
        "body{margin:0 auto;max-width:860px;padding:24px 16px;background:var(--bg);"
        "color:var(--fg);font:15px/1.55 -apple-system,'PingFang SC',sans-serif}"
        "h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 8px;color:var(--muted)}"
        ".verdict{font-weight:700}.verdict.ok{color:var(--ok)}.verdict.bad{color:var(--bad)}"
        ".meta{color:var(--muted);font-size:13px}"
        "table{border-collapse:collapse;width:100%;font-size:13.5px}"
        "th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}"
        "th{color:var(--muted);font-weight:600}"
        "code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:12.5px}"
        ".warnbox{border:1px solid var(--warn);border-radius:8px;padding:10px 12px;margin:10px 0}"
        "footer{margin-top:26px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:10px}"
        "</style></head><body>"
    )

    parts = [head]
    parts.append(
        f"<h1>舰队日报（近 {esc(d['window_hours'])}h）— "
        f"<span class=\"verdict {verdict_class}\">{verdict_text}</span></h1>"
    )
    cov_line = (
        f"总运行 {esc(d['total_runs'])} · 问题 {len(d['problems'])} · "
        f"投影积压 {esc(d['projection_backlog'])} · watchdog 覆盖：{_COVERAGE_ZH[cov['status']]}"
        f"（活跃 {len(cov['active_covered'])} · 停用 {len(cov['disabled'])} · "
        f"不支持 {len(cov['unsupported'])} · 退役 {len(cov['retired'])} · "
        f"按需 {len(cov['on_demand'])}）"
    )
    if cov["status"] == "full":
        cov_line += f" · 漏跑 {len(d['missed'])}"
    parts.append(f"<p class=\"meta\">{cov_line}</p>")

    gaps = (
        [(job, "未登记") for job in cov["observed_unregistered"]]
        + [(job, "已登记但停用") for job in cov["observed_disabled"]]
        + [(job, "已登记但 watchdog 不支持") for job in cov["observed_unsupported"]]
        + [(job, "退休后再次运行——必须显式 unretire") for job in cov["resurrected"]]
    )
    if cov["status"] == "partial":
        rows = "".join(f"<div><code>{esc(j)}</code> — {esc(r)}</div>" for j, r in gaps)
        parts.append(f"<div class=\"warnbox\"><b>watchdog 覆盖不完整</b>{rows}</div>")
    elif cov["status"] != "full":
        reason = cov["error"] or "无活跃监控的 schedules（缺失/为空/全部停用或不支持）"
        rows = "".join(f"<div><code>{esc(j)}</code> — {esc(r)}</div>" for j, r in gaps)
        parts.append(
            f"<div class=\"warnbox\"><b>watchdog coverage unavailable</b> — {esc(reason)}；"
            f"漏跑无从判定（这不是 0）{rows}</div>"
        )

    parts.append("<h2>各任务表现（execution evidence）</h2>")
    if d["jobs"]:
        trs: list[str] = []
        for job, s in sorted(d["jobs"].items()):
            mark = _STATE_MARK[_job_state(s)]
            detail = f"成 {s['succeeded']}"
            for key, zh in (("failed", "败"), ("killed", "杀"), ("spawn_failed", "起失败"),
                            ("unknown", "未知"), ("running", "跑")):
                if s[key]:
                    detail += f" / {zh} {s[key]}"
            if s["degraded"]:
                detail += f" / ⚠️degraded×{s['degraded']}"
            trs.append(
                f"<tr><td>{mark}</td><td><code>{esc(job)}</code></td>"
                f"<td>{s['total']}</td><td>{esc(detail)}</td></tr>"
            )
        parts.append(
            "<table><tr><th></th><th>任务</th><th>次数</th><th>明细</th></tr>"
            + "".join(trs) + "</table>"
        )
    else:
        parts.append("<p class=\"meta\">（窗口内无运行记录）</p>")

    if d["problems"]:
        rows = "".join(
            f"<tr><td><code>{esc(p['job'])}</code></td><td>{esc(p['status'])}</td>"
            f"<td>{esc(p.get('exit_code'))}</td><td><code>{esc(p['run_id'])}</code></td>"
            f"<td class=\"meta\">{esc(p.get('ts'))}</td></tr>"
            for p in d["problems"]
        )
        parts.append(
            "<h2>今日问题（每行可溯源）</h2><table><tr><th>任务</th><th>状态</th>"
            "<th>exit</th><th>run</th><th>时间</th></tr>" + rows + "</table>"
        )
    if d["missed"]:
        rows = "".join(
            f"<tr><td><code>{esc(m['job'])}</code></td><td>{esc(m['reason'])}</td>"
            f"<td>{esc(m.get('overdue_seconds', ''))}</td></tr>"
            for m in d["missed"]
        )
        parts.append(
            "<h2>漏跑/无覆盖（watchdog）</h2><table><tr><th>任务</th><th>原因</th>"
            "<th>超时 s</th></tr>" + rows + "</table>"
        )

    parts.append("<h2>业务结果证据（outcome evidence）</h2>")
    if outcomes["items"]:
        parts.append(
            f"<p class=\"meta\">artifact {outcomes['registered']} · eval 通过 "
            f"{outcomes['eval_pass']} / 失败 {outcomes['eval_fail']} · 审签通过 "
            f"{outcomes['approved']} / 退回 {outcomes['changes_requested']} · "
            f"必签待审 {outcomes['pending_required']}</p>"
        )
        trs2: list[str] = []
        for item in outcomes["items"]:
            state = "❌" if item in outcomes["problems"] else "⏳" if item["pending_signoff"] else "✅"
            trs2.append(
                f"<tr><td>{state}</td><td><code>{esc(item['logical_name'])}</code></td>"
                f"<td><code>{esc(str(item['sha256'])[:12])}</code></td>"
                f"<td>{esc(item['eval'] or '-')}</td><td>{esc(item['signoff'] or '-')}</td>"
                f"<td><code>{esc(item['event_id'])}</code></td></tr>"
            )
        parts.append(
            "<table><tr><th></th><th>artifact</th><th>sha256</th><th>eval</th>"
            "<th>signoff</th><th>event</th></tr>" + "".join(trs2) + "</table>"
        )
    else:
        parts.append("<p class=\"meta\">（窗口内无 artifact/eval/signoff 事件）</p>")

    parts.append(
        "<footer>execution-evidence-based：execution evidence 证明进程行为；"
        "outcome evidence 来自 artifact hash/eval/审签，两者互不替代。"
        f"静态报告文件，由 <code>qd digest --html</code> 生成 · {esc(d['generated_at'])}"
        "</footer></body></html>"
    )
    return "".join(parts)
