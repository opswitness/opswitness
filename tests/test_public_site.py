from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class _SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "img" and values.get("src"):
            self.images.append((values["src"] or "", values.get("alt")))


def _local_path(reference: str) -> Path | None:
    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc or reference.startswith("#"):
        return None
    return SITE / parsed.path


def test_public_site_identity_and_boundaries() -> None:
    body = (SITE / "index.html").read_text(encoding="utf-8")
    assert "OpsWitness" in body
    assert "Repeatable AI work for a one-person company" in body
    assert "not a hosted SaaS" in body
    assert "Community Alpha" in body
    assert "fictional customer inquiry" in body
    assert "My First Evidence Work" not in body
    assert 'id="capabilities"' in body
    assert "Run a small AI team without losing control." in body
    assert body.count("Available now") == 6
    assert "Turn a goal into a clear plan" in body
    assert "Give every AI assistant a job" in body
    assert "Stay in charge while it works" in body
    assert "Find the answer and what produced it" in body
    assert "Use good work again" in body
    assert "Keep your business workspace on your Mac" in body
    assert "Edit your AI team" in body
    assert "Build a business knowledge library" in body
    assert "not in today's download" in body
    assert "tested from a clean installation" in body
    assert "The operating layer around your AI." not in body
    assert "Agent Contract v2" not in body
    assert "source-complete" not in body
    assert "control planes" not in body
    assert "ledger, and CAS" not in body
    assert "security/advisories/new" in body
    assert "v0.1.0-alpha.1" in body
    assert body.count("Download Alpha") == 2
    assert ("releases/download/v0.1.0-alpha.1/OpsWitness-0.1.0-alpha.1-macos-arm64.dmg") in body
    assert "Ad-hoc signed" in body
    assert "not notarized" in body
    assert "sign in to Codex" in body
    assert "Anthropic API Key" not in body
    assert "Install Python" not in body
    assert "uv tool install" not in body
    assert "PUBLIC_SITE_APPROVED" in (SITE / "README.md").read_text(encoding="utf-8")
    assert (SITE / "CNAME").read_text(encoding="utf-8").strip() == "opswitness.com"


def test_public_site_local_assets_exist_and_images_have_alt_text() -> None:
    parser = _SiteParser()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))

    references = parser.links + [src for src, _alt in parser.images]
    missing = [str(path) for ref in references if (path := _local_path(ref)) and not path.is_file()]
    assert missing == []
    assert parser.images
    assert all(alt is not None for _src, alt in parser.images)


def test_public_site_uses_only_https_external_links() -> None:
    parser = _SiteParser()
    parser.feed((SITE / "index.html").read_text(encoding="utf-8"))
    external = [href for href in parser.links if urlparse(href).scheme]
    assert external
    assert all(urlparse(href).scheme == "https" for href in external)
