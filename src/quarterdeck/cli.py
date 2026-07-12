"""qd — the Quarterdeck CLI.

Subcommand map (build order):
  qd wrap  -- <cmd...>   run a job under the ledger (P2)
  qd gate  install       write Claude Code PreToolUse hook settings (P3)
  qd artifacts index     sha256-index artifact directories (P5)
  qd status              fleet at a glance
"""

from typing import TYPE_CHECKING

import typer

from quarterdeck import __version__

if TYPE_CHECKING:
    from quarterdeck.config import Settings

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def version() -> None:
    """Print the Quarterdeck version."""
    typer.echo(__version__)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def wrap(
    ctx: typer.Context,
    job: str = typer.Option(..., "--job", help="Stable job name (e.g. feed-monitor)"),
) -> None:
    """Run a command under the ledger: qd wrap --job NAME -- cmd args..."""
    from quarterdeck.wrap.runner import run_wrapped

    argv = list(ctx.args)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        typer.echo("qd wrap: no command given (usage: qd wrap --job NAME -- cmd ...)", err=True)
        raise typer.Exit(code=2)
    code = run_wrapped(job, argv)
    if code < 0:
        # Child died by a signal. The ledger is already fsync'd — mirror the death
        # faithfully by re-raising the same signal on ourselves so launchd/cron see
        # "killed by signal", not a synthetic exit code.
        import os as _os
        import signal as _signal

        sig = -code
        try:
            _signal.signal(sig, _signal.SIG_DFL)
            _os.kill(_os.getpid(), sig)
        except (OSError, ValueError):
            pass
        raise typer.Exit(code=128 + sig)  # fallback if the signal did not terminate us
    raise typer.Exit(code=code)


def _index_db(settings: "Settings"):
    return settings.ledger_dir.parent / "index.db"


@app.command()
def runs(
    job: str = typer.Option(None, "--job", help="Filter by job name"),
    limit: int = typer.Option(20, "--limit"),
) -> None:
    """Recent runs from the ledger (rebuilds the disposable SQLite index)."""
    from quarterdeck.config import Settings
    from quarterdeck.index import query_runs, rebuild
    from quarterdeck.ledger import Ledger

    settings = Settings()
    db = _index_db(settings)
    rebuild(db, Ledger(settings.ledger_dir))
    for r in query_runs(db, job=job, limit=limit):
        flag = " ⚠degraded" if r.get("degraded") else ""
        typer.echo(
            f"{r['run_id']}  {r.get('job'):<20} {r.get('status'):<9} "
            f"exit={r.get('exit_code')} {r.get('duration_s') or ''}s "
            f"{r.get('finished_ts') or r.get('started_ts')}{flag}"
        )


@app.command()
def status() -> None:
    """Fleet at a glance: per-job last state + projection backlog."""
    from quarterdeck.config import Settings
    from quarterdeck.index import job_summary, rebuild
    from quarterdeck.ledger import Ledger

    settings = Settings()
    db = _index_db(settings)
    info = rebuild(db, Ledger(settings.ledger_dir))
    for j in job_summary(db):
        mark = "✅" if j["last_status"] == "succeeded" else ("🔄" if j["last_status"] == "running" else "❌")
        typer.echo(
            f"{mark} {j['job']:<22} runs={j['runs']} failed={j['failed']} "
            f"last={j['last_status']} @ {j['last_ts']}"
        )
    typer.echo(f"\nledger runs={info['runs']} pending_projection={info['pending_projection']}")


@app.command()
def project() -> None:
    """Drain unacked ledger events into Paperclip (single-instance, at-least-once)."""
    from quarterdeck.config import Settings
    from quarterdeck.ledger import Ledger
    from quarterdeck.paperclip import PaperclipClient
    from quarterdeck.projector import Projector

    from quarterdeck.config import resolve_api_key

    settings = Settings()
    api_key = resolve_api_key(settings)
    if not api_key or not settings.paperclip.company_id:
        typer.echo(
            "qd project: need paperclip.api_key (secrets.yaml or "
            f"{settings.paperclip.api_key_env} env) and paperclip.company_id "
            "(config.yaml or QD_PAPERCLIP__COMPANY_ID)",
            err=True,
        )
        raise typer.Exit(code=2)
    client = PaperclipClient(
        settings.paperclip.api_base, api_key, settings.paperclip.company_id
    )
    projector = Projector(
        Ledger(settings.ledger_dir),
        client,
        settings.ledger_dir.parent / "projector.lease",
    )
    stats = projector.drain()
    typer.echo(
        f"projected={stats['projected']} reconciled={stats['reconciled']} "
        f"errors={stats['skipped_errors']} pending={stats['pending_after']}"
    )
    raise typer.Exit(code=0 if stats["pending_after"] == 0 else 1)


adopt_app = typer.Typer(no_args_is_help=True)
app.add_typer(adopt_app, name="adopt", help="Wrap launchd jobs (dry-run by default)")


@adopt_app.command("scan")
def adopt_scan(
    dir: str = typer.Option(
        str(__import__("pathlib").Path.home() / "Library" / "LaunchAgents"), "--dir"
    ),
) -> None:
    """Read-only inventory of launchd plists: schedule, command, wrapped state."""
    from pathlib import Path

    from quarterdeck.adopt import collisions, scan

    entries = scan(Path(dir))
    dup = collisions(entries)
    for e in entries:
        if "error" in e:
            typer.echo(f"⚠️  {e['path']}: {e['error']}")
            continue
        sched = (
            f"interval={e['expected_interval_seconds']}s"
            if "expected_interval_seconds" in e
            else f"calendar={e.get('calendar')}"
        )
        mark = "✅wrapped" if e["wrapped"] else "·"
        dup_mark = " ⚠️dup-job" if e["job"] in dup else ""
        typer.echo(f"{mark} {e['label']:<44} job={e['job']:<20} {sched}{dup_mark}")
    if dup:
        typer.echo(f"\n⚠️ job-name collisions (adopt requires explicit --job): {dup}")


@adopt_app.command("launchd")
def adopt_launchd(
    label: str,
    dir: str = typer.Option(
        str(__import__("pathlib").Path.home() / "Library" / "LaunchAgents"), "--dir"
    ),
    qd_bin: str = typer.Option("", "--qd-bin", help="Path to qd (must resolve to absolute)"),
    job_override: str = typer.Option("", "--job", help="Explicit job name (required on collision)"),
    apply_: bool = typer.Option(False, "--apply", help="Actually write (default: dry-run diff)"),
    rollback_: bool = typer.Option(False, "--rollback", help="Restore the .qd-bak backup"),
) -> None:
    """Wrap one launchd job. Without --apply this only prints the diff."""
    from pathlib import Path

    from quarterdeck.adopt import (
        apply,
        collisions,
        job_name_from_label,
        plan,
        resolve_qd_bin,
        rollback,
        scan,
    )

    plist = Path(dir) / f"{label}.plist"
    if not plist.exists():
        typer.echo(f"not found: {plist}", err=True)
        raise typer.Exit(code=2)
    if rollback_:
        ok = rollback(plist)
        typer.echo("rolled back from backup" if ok else "no backup found")
        raise typer.Exit(code=0 if ok else 1)
    job = job_override or job_name_from_label(label)
    if not job_override:
        dup = collisions(scan(Path(dir)))
        if job in dup:
            typer.echo(
                f"job name '{job}' is claimed by multiple labels: {dup[job]} — "
                f"pass an explicit --job (e.g. --job {label})",
                err=True,
            )
            raise typer.Exit(code=2)
    try:
        qd = resolve_qd_bin(qd_bin)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=2) from None
    planned = plan(plist, qd, job)
    if planned is None:
        typer.echo("already wrapped — nothing to do")
        raise typer.Exit(code=0)
    _old, new_bytes, diff = planned
    typer.echo(diff)
    if not apply_:
        typer.echo("\n(dry-run — pass --apply to write; a .qd-bak backup will be kept)")
        raise typer.Exit(code=0)
    backup = apply(plist, new_bytes)
    typer.echo(f"\nwritten. backup: {backup}")
    typer.echo(f"reload manually:\n  launchctl unload {plist}\n  launchctl load {plist}")


@app.command()
def watchdog(
    schedules_file: str = typer.Option("", "--schedules", help="YAML: jobs: [{job, expected_interval_seconds, grace_seconds}]"),
    once: bool = typer.Option(True, "--once/--loop", help="Single check (loop mode lands with P2 soak)"),
) -> None:
    """Detect missed runs from the ledger against expected schedules."""
    from datetime import UTC, datetime
    from pathlib import Path

    import yaml

    from quarterdeck.config import Settings, config_dir
    from quarterdeck.ledger import Ledger
    from quarterdeck.notify import alert
    from quarterdeck.watchdog import check

    if not once:
        typer.echo(
            "watchdog --loop is not implemented yet (lands with the P2 soak); "
            "schedule `qd watchdog --once` via launchd/cron instead",
            err=True,
        )
        raise typer.Exit(code=2)
    path = Path(schedules_file) if schedules_file else config_dir() / "schedules.yaml"
    if not path.exists():
        typer.echo(f"no schedules file at {path}", err=True)
        raise typer.Exit(code=2)
    schedules = yaml.safe_load(path.read_text()).get("jobs", [])
    settings = Settings()
    missed = check(schedules, Ledger(settings.ledger_dir).read_all(), datetime.now(UTC))
    for m in missed:
        detail = f" overdue={m['overdue_seconds']}s" if "overdue_seconds" in m else ""
        alert(f"missed run: job={m['job']} reason={m['reason']}{detail}")
        typer.echo(f"❌ {m['job']}: {m['reason']}{detail}")
    if not missed:
        typer.echo(f"✅ all {len(schedules)} scheduled jobs within expectations")
    raise typer.Exit(code=1 if missed else 0)


@app.command()
def init(
    launchagents: str = typer.Option(
        str(__import__("pathlib").Path.home() / "Library" / "LaunchAgents"), "--launchagents"
    ),
) -> None:
    """Zero-config bootstrap: detect the fleet, generate config + schedules (merge, never clobber)."""
    from pathlib import Path

    from quarterdeck.bootstrap import init_workspace
    from quarterdeck.config import config_dir

    summary = init_workspace(config_dir(), Path(launchagents))
    for path in summary["created"]:
        typer.echo(f"created: {path}")
    for path in summary["merged"]:
        typer.echo(f"merged:  {path} (your edits preserved)")
    s = summary["stats"]
    typer.echo(
        f"fleet: {s.get('discovered', 0)} jobs discovered, {s.get('added', 0)} added, "
        f"{s.get('kept', 0)} kept, {s.get('calendar_unsupported', 0)} calendar (fail-closed)"
    )
    typer.echo(
        "\nready to use:\n"
        "  qd wrap --job NAME -- <cmd>   # works now, zero further config\n"
        "  qd status / qd runs / qd digest\n"
        "  qd watchdog --once            # uses the generated schedules.yaml\n"
        "next (each needs your explicit approval):\n"
        "  qd adopt launchd <label>      # dry-run diff; --apply to wrap a real job\n"
        "  docs/INSTALL-PAPERCLIP.md     # governance UI + approvals layer"
    )


@app.command()
def digest(
    hours: int = typer.Option(24, "--hours", help="Report window"),
    telegram: bool = typer.Option(False, "--telegram", help="Also push to Telegram (secrets.yaml)"),
    schedules_file: str = typer.Option("", "--schedules", help="schedules.yaml for missed-run section"),
) -> None:
    """Daily fleet report — aggregated from the ledger (evidence, not self-reports)."""
    from datetime import UTC, datetime
    from pathlib import Path

    from quarterdeck.config import Settings, config_dir
    from quarterdeck.digest import build_digest, render_markdown
    from quarterdeck.ledger import Ledger

    settings = Settings()
    events = Ledger(settings.ledger_dir).read_all()
    missed: list = []
    sched_path = Path(schedules_file) if schedules_file else config_dir() / "schedules.yaml"
    if sched_path.exists():
        import yaml

        from quarterdeck.watchdog import check

        schedules = yaml.safe_load(sched_path.read_text()).get("jobs", [])
        missed = check(schedules, events, datetime.now(UTC))
    report = render_markdown(build_digest(events, datetime.now(UTC), hours=hours, missed=missed))
    typer.echo(report)
    if telegram:
        from quarterdeck.notify.telegram import send_telegram

        if send_telegram(report, settings):
            typer.echo("\n(sent to Telegram)", err=True)
        else:
            typer.echo("\n(telegram not configured or send failed)", err=True)
            raise typer.Exit(code=1)


@app.command()
def mcp() -> None:
    """Serve the Quarterdeck MCP console over stdio (for AionUi or any MCP client)."""
    try:
        from quarterdeck.mcp_server import build_server
    except ImportError:
        typer.echo("mcp extra not installed — pip install 'quarterdeck[mcp]'", err=True)
        raise typer.Exit(code=2) from None
    build_server().run()


if __name__ == "__main__":
    app()
