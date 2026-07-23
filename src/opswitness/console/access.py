"""Network boundary helpers for the local and private HTTPS console."""

from __future__ import annotations

import ssl
import stat
import time
from ipaddress import ip_address
from pathlib import Path
from typing import Any

from opswitness.config import ConsoleConfig


def _certificate_matches_host(decoded: dict[str, Any], public_host: str) -> bool:
    alternatives = decoded.get("subjectAltName", ())
    try:
        target_ip = ip_address(public_host)
    except ValueError:
        target_ip = None
    for kind, value in alternatives:
        if target_ip is not None and kind == "IP Address":
            try:
                if ip_address(value) == target_ip:
                    return True
            except ValueError:
                continue
        if target_ip is None and kind == "DNS":
            pattern = str(value).rstrip(".").lower()
            hostname = public_host.rstrip(".").lower()
            if pattern == hostname:
                return True
            if pattern.startswith("*."):
                suffix = pattern[1:]
                if hostname.endswith(suffix) and hostname.count(".") == pattern.count("."):
                    return True
    return False


def console_public_url(config: ConsoleConfig) -> str:
    if config.exposure == "loopback":
        return f"http://127.0.0.1:{config.port}"
    public_port = config.public_port
    if public_port is None:
        public_port = 443 if config.private_transport == "trusted_loopback_proxy" else config.port
    port = "" if public_port == 443 else f":{public_port}"
    return f"https://{config.public_host}{port}"


def console_allowed_hosts(config: ConsoleConfig) -> set[str]:
    hosts = {"127.0.0.1", "localhost", "::1"}
    if config.exposure == "private":
        hosts.add(config.public_host.rstrip(".").lower())
        if config.host not in {"0.0.0.0", "::"}:
            hosts.add(config.host)
    return hosts


def console_local_origins(config: ConsoleConfig) -> set[str]:
    """Return exact browser origins served by the local console listener."""
    scheme = (
        "https"
        if config.exposure == "private" and config.private_transport == "direct_tls"
        else "http"
    )
    return {
        f"{scheme}://127.0.0.1:{config.port}",
        f"{scheme}://localhost:{config.port}",
        f"{scheme}://[::1]:{config.port}",
    }


def console_public_origins(config: ConsoleConfig) -> set[str]:
    """Return the exact HTTPS origin allowed for paired private devices."""
    if config.exposure != "private":
        return set()
    return {console_public_url(config)}


def validate_private_tls(config: ConsoleConfig) -> tuple[Path, Path]:
    """Validate the configured cert/key before opening a private listener."""
    if config.exposure != "private" or config.private_transport != "direct_tls":
        raise ValueError("TLS files are only valid for private direct_tls exposure")
    assert config.tls_certfile is not None
    assert config.tls_keyfile is not None
    cert = config.tls_certfile.expanduser()
    key = config.tls_keyfile.expanduser()
    for path, label in ((cert, "TLS certificate"), (key, "TLS private key")):
        if path.is_symlink():
            raise ValueError(f"{label} must not be a symlink: {path}")
        try:
            metadata = path.stat()
        except FileNotFoundError as exc:
            raise ValueError(f"{label} does not exist: {path}") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError(f"{label} must be a regular file: {path}")
    if stat.S_IMODE(key.stat().st_mode) & 0o077:
        raise ValueError(f"TLS private key must not be group/world accessible: {key}")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(str(cert), str(key))
        decoded = ssl._ssl._test_decode_cert(str(cert))  # type: ignore[attr-defined]  # noqa: SLF001
        if not _certificate_matches_host(decoded, config.public_host):
            raise ssl.CertificateError(
                f"certificate subjectAltName does not match {config.public_host}"
            )
    except (OSError, ssl.SSLError, ssl.CertificateError, ValueError) as exc:
        raise ValueError(f"TLS certificate validation failed: {exc}") from exc

    now = time.time()
    not_before = decoded.get("notBefore")
    not_after = decoded.get("notAfter")
    if not_before and ssl.cert_time_to_seconds(not_before) > now:
        raise ValueError("TLS certificate is not valid yet")
    if not_after and ssl.cert_time_to_seconds(not_after) <= now:
        raise ValueError("TLS certificate has expired")
    return cert.resolve(), key.resolve()
