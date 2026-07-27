"""Frozen executable entrypoint for the desktop-owned OpsWitness backend."""

from opswitness.cli import app


if __name__ == "__main__":
    app()
