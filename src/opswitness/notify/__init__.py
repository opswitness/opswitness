"""Alert fan-out. Console/stderr for now; Telegram is an optional integration."""

import sys


def alert(message: str) -> None:
    print(f"[opswitness:alert] {message}", file=sys.stderr, flush=True)
