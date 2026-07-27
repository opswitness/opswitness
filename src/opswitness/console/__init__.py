"""OpsWitness's loopback-only total console."""

from typing import Any

__all__ = ["create_app"]


def __getattr__(name: str) -> Any:
    """Keep the public factory lazy so schema-only modules cannot form a cycle."""
    if name == "create_app":
        from opswitness.console.app import create_app

        return create_app
    raise AttributeError(name)
