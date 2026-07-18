"""Alert fan-out. Console/stderr for now; Telegram channel lands with `qd gate` (P3)."""

import sys


def alert(message: str) -> None:
    print(f"[qd:alert] {message}", file=sys.stderr, flush=True)
