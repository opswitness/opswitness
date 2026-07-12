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
    raise typer.Exit(code=run_wrapped(job, argv))


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
    import os as _os

    from quarterdeck.config import Settings
    from quarterdeck.ledger import Ledger
    from quarterdeck.paperclip import PaperclipClient
    from quarterdeck.projector import Projector

    settings = Settings()
    api_key = _os.environ.get(settings.paperclip.api_key_env, "")
    if not api_key or not settings.paperclip.company_id:
        typer.echo(
            f"qd project: need {settings.paperclip.api_key_env} env and paperclip.company_id "
            f"config (QD_PAPERCLIP__COMPANY_ID)",
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


if __name__ == "__main__":
    app()
