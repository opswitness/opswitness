from __future__ import annotations

import json
import shutil
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from opswitness.config import Settings
from opswitness.console.access import (
    console_local_origins,
    console_public_origins,
    validate_private_tls,
)
from opswitness.console.app import create_app
from opswitness.console.pairing import (
    DevicePairingStore,
    InvalidPairingCode,
    PAIRING_COOKIE,
    PairingLocked,
    PairingStateError,
)


@pytest.fixture(autouse=True)
def _isolate_opswitness_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir(mode=0o700)
    monkeypatch.setenv("OPSWITNESS_CONFIG_DIR", str(config_root))


class _ConsoleService:
    def acquire_instance_lease(self) -> bool:
        return True

    def recover_startup(self) -> dict[str, object]:
        return {}

    def release_instance_lease(self) -> None:
        return None

    def close(self) -> None:
        return None

    def dashboard(self) -> dict[str, object]:
        return {
            "generated_at": "now",
            "integrations": {},
            "providers": {},
            "system": {},
            "fleet": {
                "runs": 0,
                "artifacts": 0,
                "pending_projection": 0,
                "jobs": 0,
                "monitored_jobs": 0,
                "healthy_jobs": 0,
                "problem_jobs": 0,
                "missed_jobs": 0,
                "coverage_status": "none",
                "fleet_healthy": False,
            },
            "pending_approvals": 0,
            "approvals_available": True,
            "approvals": [],
            "workflows": [],
            "plans": [],
            "task_runs": [],
            "recent_runs": [],
            "mail_ready": False,
            "home": {},
            "team_blueprints": [],
            "runtime_capabilities": [],
        }


def _private_settings(tmp_path: Path, *, public_host: str = "deck.test") -> Settings:
    return Settings(
        console={
            "exposure": "private",
            "host": "0.0.0.0",
            "port": 8765,
            "public_host": public_host,
            "tls_certfile": tmp_path / "deck.crt",
            "tls_keyfile": tmp_path / "deck.key",
            "state_dir": tmp_path / "console",
        },
        ledger_dir=tmp_path / "ledger",
    )


def _proxy_settings(tmp_path: Path) -> Settings:
    return Settings(
        console={
            "exposure": "private",
            "private_transport": "trusted_loopback_proxy",
            "host": "127.0.0.1",
            "port": 8765,
            "public_host": "deck.test",
            "state_dir": tmp_path / "console",
        },
        ledger_dir=tmp_path / "ledger",
    )


def _remote_client(
    settings: Settings,
    store: DevicePairingStore,
    *,
    scheme: str = "https",
    follow_redirects: bool = False,
) -> TestClient:
    return TestClient(
        create_app(settings, service=_ConsoleService(), pairing_store=store),
        base_url=f"{scheme}://deck.test:8765",
        follow_redirects=follow_redirects,
        client=("192.168.68.50", 50123),
    )


def test_private_console_requires_https_pairing_and_nonreplayable_code(tmp_path):
    settings = _private_settings(tmp_path)
    store = DevicePairingStore(settings.console.state_dir / "pairing")

    with _remote_client(settings, store) as client:
        denied = client.get("/api/v1/bootstrap")
        assert denied.status_code == 401
        assert denied.json()["code"] == "pairing_required"
        redirect = client.get("/")
        assert redirect.status_code == 303
        assert redirect.headers["location"] == "/pair"
        pair_page = client.get("/pair")
        assert pair_page.status_code == 200
        assert "Pair this device" in pair_page.text

        invitation = store.create_invitation()
        missing_origin = client.post(
            "/api/v1/pairing/claim",
            json={"code": invitation.code, "device_name": "iPhone"},
        )
        assert missing_origin.status_code == 403
        paired = client.post(
            "/api/v1/pairing/claim",
            json={"code": invitation.code, "device_name": "iPhone"},
            headers={"Origin": "https://deck.test:8765"},
        )
        assert paired.status_code == 200
        cookie = paired.headers["set-cookie"]
        assert PAIRING_COOKIE in cookie
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie

        bootstrap = client.get("/api/v1/bootstrap")
        assert bootstrap.status_code == 200
        assert bootstrap.json()["console_access"] == {
            "exposure": "private",
            "public_url": "https://deck.test:8765",
            "paired": True,
            "can_manage_devices": True,
        }
        assert client.post("/api/v1/pairing/invitations", json={"confirmed": True}).status_code == 403

        csrf = bootstrap.json()["csrf_token"]
        devices = client.get("/api/v1/pairing/devices")
        assert devices.status_code == 200
        assert devices.json()[0]["name"] == "iPhone"
        assert "token_hash" not in devices.text
        device_id = devices.json()[0]["device_id"]
        revoked = client.post(
            f"/api/v1/pairing/devices/{device_id}/revoke",
            json={"confirmed": True},
            headers={"Origin": "https://deck.test:8765", "X-QD-CSRF": csrf},
        )
        assert revoked.status_code == 200
        assert client.get("/api/v1/bootstrap").status_code == 401

    with _remote_client(settings, store) as replay_client:
        replay = replay_client.post(
            "/api/v1/pairing/claim",
            json={"code": invitation.code, "device_name": "Replay"},
            headers={"Origin": "https://deck.test:8765"},
        )
        assert replay.status_code == 403


def test_private_console_rejects_plain_http_bad_host_and_cross_origin(tmp_path):
    settings = _private_settings(tmp_path)
    store = DevicePairingStore(settings.console.state_dir / "pairing")
    with _remote_client(settings, store, scheme="http") as client:
        response = client.get("/pair")
        assert response.status_code == 426
        assert response.headers["upgrade"] == "TLS/1.2"

    with _remote_client(settings, store) as client:
        assert client.get("/api/health", headers={"Host": "rebound.example"}).status_code == 400
        invitation = store.create_invitation()
        for origin in (
            "https://evil.example",
            "https://deck.test:9443",
            "https://127.0.0.1:8765",
            "null",
        ):
            denied = client.post(
                "/api/v1/pairing/claim",
                json={"code": invitation.code, "device_name": "Phone"},
                headers={"Origin": origin},
            )
            assert denied.status_code == 403
            assert denied.json() == {"detail": "origin denied", "code": "origin_denied"}


def test_loopback_client_can_bootstrap_private_console_and_create_first_invitation(tmp_path):
    settings = _private_settings(tmp_path)
    store = DevicePairingStore(settings.console.state_dir / "pairing")
    app = create_app(settings, service=_ConsoleService(), pairing_store=store)
    with TestClient(
        app,
        base_url="https://127.0.0.1:8765",
        client=("127.0.0.1", 50123),
    ) as client:
        bootstrap = client.get("/api/v1/bootstrap")
        assert bootstrap.status_code == 200
        csrf = bootstrap.json()["csrf_token"]
        wrong_origin = client.post(
            "/api/v1/pairing/invitations",
            json={"confirmed": True},
            headers={"Origin": "https://evil.example", "X-QD-CSRF": csrf},
        )
        assert wrong_origin.status_code == 403
        assert wrong_origin.json()["code"] == "origin_denied"
        invitation = client.post(
            "/api/v1/pairing/invitations",
            json={"confirmed": True},
            headers={"Origin": "https://127.0.0.1:8765", "X-QD-CSRF": csrf},
        )
        assert invitation.status_code == 201
        assert invitation.json()["public_url"] == "https://deck.test:8765"
        assert invitation.json()["code"].count("-") == 2


def test_trusted_loopback_proxy_requires_exact_host_and_forwarded_https(tmp_path):
    settings = _proxy_settings(tmp_path)
    store = DevicePairingStore(settings.console.state_dir / "pairing")
    app = create_app(settings, service=_ConsoleService(), pairing_store=store)
    invitation = store.create_invitation()
    claim = store.claim(invitation.code, "Chrome on iPhone")

    with TestClient(
        app,
        base_url="http://deck.test:8765",
        client=("127.0.0.1", 50123),
        follow_redirects=False,
    ) as client:
        assert client.get("/pair").status_code == 426
        paired = client.get(
            "/api/v1/bootstrap",
            headers={
                "X-Forwarded-Proto": "https",
                "Cookie": f"{PAIRING_COOKIE}={claim.token}",
            },
        )
        assert paired.status_code == 200
        assert paired.json()["console_access"]["public_url"] == "https://deck.test"
        assert paired.headers["strict-transport-security"] == "max-age=31536000"

    with TestClient(
        app,
        base_url="http://deck.test:8765",
        client=("192.168.68.50", 50123),
    ) as remote_client:
        spoofed = remote_client.get("/pair", headers={"X-Forwarded-Proto": "https"})
        assert spoofed.status_code == 426

    with TestClient(
        app,
        base_url="http://127.0.0.1:8765",
        client=("127.0.0.1", 50123),
    ) as local_client:
        bootstrap = local_client.get("/api/v1/bootstrap")
        assert bootstrap.status_code == 200
        invitation = local_client.post(
            "/api/v1/pairing/invitations",
            json={"confirmed": True},
            headers={
                "Origin": "http://127.0.0.1:8765",
                "X-QD-CSRF": bootstrap.json()["csrf_token"],
            },
        )
        assert invitation.status_code == 201

    with TestClient(
        app,
        base_url="http://localhost:8765",
        client=("127.0.0.1", 50124),
    ) as localhost_client:
        bootstrap = localhost_client.get("/api/v1/bootstrap")
        invitation = localhost_client.post(
            "/api/v1/pairing/invitations",
            json={"confirmed": True},
            headers={
                "Origin": "http://localhost:8765",
                "X-QD-CSRF": bootstrap.json()["csrf_token"],
            },
        )
        assert invitation.status_code == 201

    with TestClient(
        app,
        base_url="http://localhost:8765",
        client=("::1", 50125),
    ) as ipv6_client:
        bootstrap = ipv6_client.get(
            "/api/v1/bootstrap",
            headers={"Host": "[::1]:8765"},
        )
        invitation = ipv6_client.post(
            "/api/v1/pairing/invitations",
            json={"confirmed": True},
            headers={
                "Host": "[::1]:8765",
                "Origin": "http://[::1]:8765",
                "X-QD-CSRF": bootstrap.json()["csrf_token"],
            },
        )
        assert invitation.status_code == 201


def test_private_origin_sets_separate_local_listener_and_public_proxy(tmp_path):
    direct = _private_settings(tmp_path)
    assert console_local_origins(direct.console) == {
        "https://127.0.0.1:8765",
        "https://localhost:8765",
        "https://[::1]:8765",
    }
    assert console_public_origins(direct.console) == {"https://deck.test:8765"}

    proxy = _proxy_settings(tmp_path)
    assert console_local_origins(proxy.console) == {
        "http://127.0.0.1:8765",
        "http://localhost:8765",
        "http://[::1]:8765",
    }
    assert console_public_origins(proxy.console) == {"https://deck.test"}


def test_pairing_store_hashes_credentials_expires_and_rate_limits(tmp_path):
    now = [datetime(2026, 7, 14, 12, 0, tzinfo=UTC)]
    store = DevicePairingStore(
        tmp_path / "pairing",
        code_ttl_seconds=60,
        session_days=1,
        clock=lambda: now[0],
    )
    invitation = store.create_invitation()
    claim = store.claim(invitation.code, "Safari on iPhone")
    state_text = (tmp_path / "pairing" / "devices.json").read_text()
    assert invitation.code not in state_text
    assert claim.token not in state_text
    assert stat.S_IMODE((tmp_path / "pairing" / "devices.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "pairing").stat().st_mode) == 0o700
    assert store.validate_token(claim.token).name == "Safari on iPhone"
    with pytest.raises(InvalidPairingCode):
        store.claim(invitation.code, "Replay")

    for _ in range(4):
        with pytest.raises(InvalidPairingCode):
            store.claim("2222-2222-2222", "Invalid")
    with pytest.raises(PairingLocked):
        store.claim("2222-2222-2222", "Locked")

    now[0] += timedelta(days=2)
    assert store.validate_token(claim.token) is None


def test_pairing_store_fails_closed_on_corrupt_or_world_readable_state(tmp_path):
    root = tmp_path / "pairing"
    root.mkdir(mode=0o700)
    state = root / "devices.json"
    state.write_text("{}")
    state.chmod(0o644)
    store = DevicePairingStore(root)
    with pytest.raises(PairingStateError, match="0600"):
        store.list_devices()
    state.chmod(0o600)
    state.write_text("not-json")
    with pytest.raises(PairingStateError, match="invalid"):
        store.list_devices()


def test_private_console_config_and_tls_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="tls_certfile"):
        Settings(console={"exposure": "private", "host": "0.0.0.0", "public_host": "deck.test"})
    with pytest.raises(ValueError, match="private or wildcard"):
        Settings(
            console={
                "exposure": "private",
                "host": "8.8.8.8",
                "public_host": "deck.test",
                "tls_certfile": tmp_path / "deck.crt",
                "tls_keyfile": tmp_path / "deck.key",
            }
        )
    with pytest.raises(ValueError, match="must bind"):
        Settings(
            console={
                "exposure": "private",
                "private_transport": "trusted_loopback_proxy",
                "host": "0.0.0.0",
                "public_host": "deck.test",
            }
        )
    tailscale_address = Settings(
        console={
            "exposure": "private",
            "host": "100.100.101.102",
            "public_host": "deck.test",
            "tls_certfile": tmp_path / "deck.crt",
            "tls_keyfile": tmp_path / "deck.key",
        }
    )
    assert tailscale_address.console.host == "100.100.101.102"

    settings = _private_settings(tmp_path)
    with pytest.raises(ValueError, match="does not exist"):
        validate_private_tls(settings.console)


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl is unavailable")
def test_private_tls_certificate_must_match_public_host(tmp_path):
    cert = tmp_path / "deck.crt"
    key = tmp_path / "deck.key"
    subprocess.run(
        [
            shutil.which("openssl") or "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=deck.test",
            "-addext",
            "subjectAltName=DNS:deck.test",
        ],
        check=True,
        capture_output=True,
    )
    key.chmod(0o600)
    settings = _private_settings(tmp_path)
    assert validate_private_tls(settings.console) == (cert.resolve(), key.resolve())
    wrong_host = settings.console.model_copy(update={"public_host": "wrong.test"})
    with pytest.raises(ValueError, match="certificate validation failed"):
        validate_private_tls(wrong_host)


def test_pwa_shell_never_caches_api_or_business_responses(tmp_path):
    settings = _private_settings(tmp_path)
    store = DevicePairingStore(settings.console.state_dir / "pairing")
    with _remote_client(settings, store) as client:
        worker = client.get("/sw.js")
        assert worker.status_code == 200
        assert "url.pathname.startsWith('/api/')" in worker.text
        assert "caches.open(CACHE_NAME)" in worker.text
        manifest = client.get("/manifest.webmanifest")
        assert manifest.status_code == 200
        assert json.loads(manifest.text)["display"] == "standalone"
        assert client.get("/api/v1/bootstrap").headers["cache-control"] == "no-store"
