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
    visible_text = " ".join(body.split())
    assert "OpsWitness" in visible_text
    assert "Repeatable AI work for a one-person company" in visible_text
    assert "not a hosted SaaS" in visible_text
    assert "Community Alpha" in visible_text
    assert "security/advisories/new" in body
    assert "Release candidate validation in progress" in body
    assert "/releases/download/" not in body
    assert "/releases/tag/" not in body
    assert (ROOT / "docs" / "QUICKSTART.md").is_file()
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
