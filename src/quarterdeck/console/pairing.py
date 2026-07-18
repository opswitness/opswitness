"""Crash-safe, local-only state for private-console device pairing."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import stat
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from quarterdeck.fsutil import atomic_write
from quarterdeck.ids import new_ulid

PAIRING_COOKIE = "__Host-qd_device"
PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
PAIRING_CODE_LENGTH = 12
PAIRING_FAILURE_LIMIT = 5
PAIRING_FAILURE_WINDOW_SECONDS = 60


class PairingStateError(RuntimeError):
    pass


class InvalidPairingCode(ValueError):
    pass


class PairingLocked(ValueError):
    pass


class _Invitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_id: str
    code_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    expires_at: datetime


class PairedDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str
    name: str = Field(min_length=1, max_length=80)
    token_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime

    def public_dict(self) -> dict[str, str]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


class _PairingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    invitations: list[_Invitation] = Field(default_factory=list, max_length=4)
    devices: list[PairedDevice] = Field(default_factory=list, max_length=32)
    failed_attempts: list[datetime] = Field(default_factory=list, max_length=32)


@dataclass(frozen=True)
class PairingInvitation:
    invitation_id: str
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class PairingClaim:
    device_id: str
    token: str
    expires_at: datetime


class DevicePairingStore:
    def __init__(
        self,
        root: Path,
        *,
        code_ttl_seconds: int = 600,
        session_days: int = 90,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = root.expanduser()
        self.state_path = self.root / "devices.json"
        self.lock_path = self.root / ".pairing.lock"
        self.code_ttl_seconds = code_ttl_seconds
        self.session_days = session_days
        self._clock = clock or (lambda: datetime.now(UTC))

    def create_invitation(self) -> PairingInvitation:
        now = self._now()
        code = self._new_code()
        invitation = _Invitation(
            invitation_id=new_ulid(),
            code_hash=self._hash("code", self._normalize_code(code)),
            created_at=now,
            expires_at=now + timedelta(seconds=self.code_ttl_seconds),
        )
        with self._locked():
            state = self._read()
            self._purge(state, now)
            state.invitations = [invitation]
            self._write(state)
        return PairingInvitation(
            invitation_id=invitation.invitation_id,
            code=code,
            expires_at=invitation.expires_at,
        )

    def claim(self, code: str, device_name: str) -> PairingClaim:
        name = " ".join(device_name.strip().split())
        if not name or len(name) > 80:
            raise InvalidPairingCode("device name must contain 1-80 characters")
        normalization_error: ValueError | None
        try:
            normalized = self._normalize_code(code)
        except ValueError as exc:
            normalized = ""
            normalization_error = exc
        else:
            normalization_error = None
        now = self._now()
        with self._locked():
            state = self._read()
            self._purge(state, now)
            cutoff = now - timedelta(seconds=PAIRING_FAILURE_WINDOW_SECONDS)
            state.failed_attempts = [row for row in state.failed_attempts if row >= cutoff]
            if len(state.failed_attempts) >= PAIRING_FAILURE_LIMIT:
                self._write(state)
                raise PairingLocked("too many pairing attempts; wait one minute")
            expected = self._hash("code", normalized) if normalized else ""
            matched = next(
                (
                    invitation
                    for invitation in state.invitations
                    if secrets.compare_digest(invitation.code_hash, expected)
                ),
                None,
            )
            if normalization_error is not None or matched is None:
                state.failed_attempts.append(now)
                self._write(state)
                raise InvalidPairingCode("pairing code is invalid or expired")
            if len(state.devices) >= 32:
                raise PairingStateError("paired device limit reached")
            token = secrets.token_urlsafe(32)
            device = PairedDevice(
                device_id=new_ulid(),
                name=name,
                token_hash=self._hash("token", token),
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=self.session_days),
            )
            state.invitations = [
                invitation
                for invitation in state.invitations
                if invitation.invitation_id != matched.invitation_id
            ]
            state.failed_attempts = []
            state.devices.append(device)
            self._write(state)
        return PairingClaim(
            device_id=device.device_id,
            token=token,
            expires_at=device.expires_at,
        )

    def validate_token(self, token: str | None) -> PairedDevice | None:
        if not token or len(token) > 256:
            return None
        now = self._now()
        expected = self._hash("token", token)
        with self._locked():
            state = self._read()
            changed = self._purge(state, now)
            device = next(
                (
                    row
                    for row in state.devices
                    if secrets.compare_digest(row.token_hash, expected)
                ),
                None,
            )
            if device is not None and now - device.last_seen_at >= timedelta(minutes=5):
                device.last_seen_at = now
                changed = True
            if changed:
                self._write(state)
            return device.model_copy(deep=True) if device is not None else None

    def list_devices(self) -> list[PairedDevice]:
        now = self._now()
        with self._locked():
            state = self._read()
            if self._purge(state, now):
                self._write(state)
            return [row.model_copy(deep=True) for row in state.devices]

    def revoke(self, device_id: str) -> bool:
        now = self._now()
        with self._locked():
            state = self._read()
            self._purge(state, now)
            before = len(state.devices)
            state.devices = [row for row in state.devices if row.device_id != device_id]
            changed = len(state.devices) != before
            if changed:
                self._write(state)
            return changed

    def revoke_token(self, token: str | None) -> bool:
        if not token:
            return False
        expected = self._hash("token", token)
        now = self._now()
        with self._locked():
            state = self._read()
            self._purge(state, now)
            before = len(state.devices)
            state.devices = [
                row
                for row in state.devices
                if not secrets.compare_digest(row.token_hash, expected)
            ]
            changed = len(state.devices) != before
            if changed:
                self._write(state)
            return changed

    def _ensure(self) -> None:
        if self.root.is_symlink():
            raise PairingStateError("pairing state directory must not be a symlink")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._ensure()
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.lock_path, flags, 0o600)
        except OSError as exc:
            raise PairingStateError(f"cannot open pairing lock: {exc}") from exc
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self) -> _PairingState:
        if not self.state_path.exists():
            return _PairingState()
        if self.state_path.is_symlink():
            raise PairingStateError("pairing state file must not be a symlink")
        if stat.S_IMODE(self.state_path.stat().st_mode) != 0o600:
            raise PairingStateError("pairing state file mode must be 0600")
        try:
            return _PairingState.model_validate_json(self.state_path.read_text())
        except (OSError, ValueError) as exc:
            raise PairingStateError(f"pairing state is invalid: {exc}") from exc

    def _write(self, state: _PairingState) -> None:
        payload = (
            json.dumps(state.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
            + "\n"
        ).encode()
        atomic_write(self.state_path, payload, mode=0o600)

    @staticmethod
    def _purge(state: _PairingState, now: datetime) -> bool:
        invitations = [row for row in state.invitations if row.expires_at > now]
        devices = [row for row in state.devices if row.expires_at > now]
        changed = len(invitations) != len(state.invitations) or len(devices) != len(state.devices)
        state.invitations = invitations
        state.devices = devices
        return changed

    def _now(self) -> datetime:
        value = self._clock()
        return value.astimezone(UTC)

    @staticmethod
    def _hash(kind: str, value: str) -> str:
        return hashlib.sha256(f"quarterdeck-pairing-v1:{kind}:{value}".encode()).hexdigest()

    @staticmethod
    def _new_code() -> str:
        raw = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))
        return "-".join(raw[index : index + 4] for index in range(0, len(raw), 4))

    @staticmethod
    def _normalize_code(code: str) -> str:
        normalized = "".join(character for character in code.upper() if character not in " -")
        if len(normalized) != PAIRING_CODE_LENGTH or any(
            character not in PAIRING_ALPHABET for character in normalized
        ):
            raise ValueError("invalid pairing code format")
        return normalized
