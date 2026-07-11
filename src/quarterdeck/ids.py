"""Monotonic ULID generation (Crockford base32, 48-bit ms timestamp + 80-bit randomness).

Dependency-free. Within one process, ULIDs are strictly monotonic even inside the same
millisecond (random段 increments), so lexicographic order == creation order — the ledger's
oldest-first projector relies on this.
"""

import os
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_lock = threading.Lock()
_last_ts = -1
_last_rand = 0


def new_ulid() -> str:
    global _last_ts, _last_rand
    with _lock:
        ts = int(time.time() * 1000) & ((1 << 48) - 1)
        if ts == _last_ts:
            _last_rand = (_last_rand + 1) & ((1 << 80) - 1)
        else:
            _last_ts = ts
            _last_rand = int.from_bytes(os.urandom(10), "big")
        value = (ts << 80) | _last_rand
    chars = []
    for _ in range(26):
        chars.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))
