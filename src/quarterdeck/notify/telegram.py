"""Telegram delivery — paragraph-aware chunking, optional HTML parse mode.

Config from secrets.yaml (never the repo). Chunks split at paragraph (blank-line)
boundaries where possible so a chunk never breaks mid-line, falling back to a hard
cut only for a single oversized paragraph.
"""

import httpx

from quarterdeck.config import Settings

_CHUNK = 3900  # Telegram hard limit 4096; headroom for entities


def _split(text: str) -> list[str]:
    if len(text) <= _CHUNK:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        while len(para) > _CHUNK:  # single oversized paragraph: hard cut at a line if possible
            cut = para.rfind("\n", 0, _CHUNK)
            cut = cut if cut > 0 else _CHUNK
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:cut])
            para = para[cut:].lstrip("\n")
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > _CHUNK:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_telegram(text: str, settings: Settings, parse_mode: str | None = None) -> bool:
    token = settings.telegram.bot_token
    chat_id = settings.telegram.chat_id
    if not token or not chat_id:
        return False
    ok = True
    with httpx.Client(timeout=15) as client:
        for chunk in _split(text):
            payload: dict = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                payload["parse_mode"] = parse_mode
            try:
                resp = client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage", json=payload
                )
                ok = ok and resp.status_code == 200
            except httpx.HTTPError:
                ok = False
    return ok
