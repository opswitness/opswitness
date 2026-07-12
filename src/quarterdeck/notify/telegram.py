"""Telegram delivery — chunked sendMessage, config from secrets.yaml (never the repo)."""

import httpx

from quarterdeck.config import Settings

_CHUNK = 3900  # Telegram hard limit 4096; headroom for entities


def _split(text: str) -> list[str]:
    chunks: list[str] = []
    while text:
        chunks.append(text[:_CHUNK])
        text = text[_CHUNK:]
    return chunks


def send_telegram(text: str, settings: Settings) -> bool:
    token = settings.telegram.bot_token
    chat_id = settings.telegram.chat_id
    if not token or not chat_id:
        return False
    ok = True
    with httpx.Client(timeout=15) as client:
        for chunk in _split(text):
            try:
                resp = client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk},
                )
                ok = ok and resp.status_code == 200
            except httpx.HTTPError:
                ok = False
    return ok
