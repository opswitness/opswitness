from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import yaml


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


def test_pages_deployment_is_release_gated_and_verifies_the_alpha_dmg() -> None:
    workflow = yaml.load(
        (ROOT / ".github" / "workflows" / "pages.yml").read_text(),
        Loader=yaml.BaseLoader,
    )
    deploy = workflow["jobs"]["deploy"]
    assert "PUBLIC_SITE_APPROVED" in deploy["if"]
    assert "PUBLIC_RELEASE_APPROVED" in deploy["if"]
    steps = deploy["steps"]
    download = next(
        step for step in steps if step.get("name") == "Download the exact Alpha package"
    )
    assert "gh release view" in download["run"]
    assert "gh release download" in download["run"]
    assert "OpsWitness-0.1.0-alpha.1-macos-arm64.dmg" in download["run"]
    assert "SHA256SUMS" in download["run"]
    assert "v0.1.0-alpha.1" in download["env"]["RELEASE_TAG"]
    verify = next(
        step
        for step in steps
        if step.get("name") == "Verify the ad-hoc Alpha package"
    )
    assert "isPrerelease" in verify["run"]
    assert "sha256" in verify["run"]
    assert "release checksum mismatch" in verify["run"]
    assert "developer-id" not in verify["run"]
    assert "notarization" not in verify["run"]
    upload = next(
        step for step in steps if step.get("uses", "").startswith("actions/upload-pages-artifact@")
    )
    assert upload["with"]["path"] == "site"
