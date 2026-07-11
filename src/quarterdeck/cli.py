"""qd — the Quarterdeck CLI.

Subcommand map (build order):
  qd wrap  -- <cmd...>   run a job under the ledger (P2)
  qd gate  install       write Claude Code PreToolUse hook settings (P3)
  qd artifacts index     sha256-index artifact directories (P5)
  qd status              fleet at a glance
"""

import typer

from quarterdeck import __version__

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def version() -> None:
    """Print the Quarterdeck version."""
    typer.echo(__version__)


@app.command()
def status() -> None:
    """Fleet at a glance (jobs, last runs, pending approvals)."""
    typer.echo("not implemented yet — see roadmap in README")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
