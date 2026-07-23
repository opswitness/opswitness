"""Bounded, PID-reuse-safe process-tree signalling outside signal handlers."""

from __future__ import annotations

import os
import signal
import time
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Protocol

import psutil


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float
    depth: int


@dataclass
class TreeSignalResult:
    requested_signal: int
    final_signal: int
    survivors: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pid_reused: list[int] = field(default_factory=list)

    @property
    def degraded(self) -> bool:
        return bool(self.survivors or self.errors)


class ProcessInspector(Protocol):
    def snapshot(self, root_pid: int) -> list[ProcessIdentity]: ...

    def alive(self, identity: ProcessIdentity) -> bool: ...

    def send(self, identity: ProcessIdentity, signum: int) -> None: ...


class PsutilInspector:
    def snapshot(self, root_pid: int) -> list[ProcessIdentity]:
        root = psutil.Process(root_pid)
        found: list[ProcessIdentity] = []

        def walk(process: psutil.Process, depth: int) -> None:
            for child in process.children():
                try:
                    identity = ProcessIdentity(child.pid, child.create_time(), depth)
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    continue
                found.append(identity)
                walk(child, depth + 1)

        try:
            root_identity = ProcessIdentity(root.pid, root.create_time(), 0)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return []
        found.append(root_identity)
        walk(root, 1)
        return found

    def alive(self, identity: ProcessIdentity) -> bool:
        try:
            process = psutil.Process(identity.pid)
            if abs(process.create_time() - identity.create_time) > 0.001:
                return False
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return False

    def send(self, identity: ProcessIdentity, signum: int) -> None:
        process = psutil.Process(identity.pid)
        if abs(process.create_time() - identity.create_time) > 0.001:
            raise ProcessLookupError(f"pid {identity.pid} was reused")
        process.send_signal(signum)


def signal_process_tree(
    root_pid: int,
    signum: int,
    *,
    inspector: ProcessInspector | None = None,
    budget_seconds: float = 1.0,
    force_after_seconds: float = 0.75,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    group_signal: Callable[[int, int], None] = os.killpg,
) -> TreeSignalResult:
    """Signal a snapshotted tree, verify it, and force survivors within one budget."""
    inspector = inspector or PsutilInspector()
    result = TreeSignalResult(requested_signal=signum, final_signal=signum)
    started = clock()
    try:
        identities = inspector.snapshot(root_pid)
    except (OSError, psutil.Error) as exc:
        identities = []
        result.errors.append(f"snapshot:{type(exc).__name__}:{exc}")

    try:
        group_signal(root_pid, signum)
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        result.errors.append(f"killpg:PermissionError:{exc}")
    except OSError as exc:
        result.errors.append(f"killpg:{type(exc).__name__}:{exc}")

    forced = False
    while identities and clock() - started < budget_seconds:
        survivors: list[ProcessIdentity] = []
        for identity in identities:
            try:
                if inspector.alive(identity):
                    survivors.append(identity)
            except (OSError, psutil.Error) as exc:
                result.errors.append(f"inspect:{identity.pid}:{type(exc).__name__}:{exc}")
                survivors.append(identity)
        if not survivors:
            identities = []
            break

        elapsed = clock() - started
        send_signal = signal.SIGKILL if elapsed >= force_after_seconds else signum
        if send_signal == signal.SIGKILL:
            forced = True
        for identity in sorted(survivors, key=lambda item: item.depth, reverse=True):
            try:
                inspector.send(identity, send_signal)
            except ProcessLookupError:
                result.pid_reused.append(identity.pid)
            except (PermissionError, OSError, psutil.Error) as exc:
                result.errors.append(
                    f"signal:{identity.pid}:{type(exc).__name__}:{exc}"
                )
        identities = survivors
        sleeper(min(0.05, max(0.0, budget_seconds - (clock() - started))))

    result.final_signal = signal.SIGKILL if forced else signum
    result.survivors = sorted(
        identity.pid
        for identity in identities
        if _safe_alive(inspector, identity, result)
    )
    return result


def _safe_alive(
    inspector: ProcessInspector,
    identity: ProcessIdentity,
    result: TreeSignalResult,
) -> bool:
    try:
        return inspector.alive(identity)
    except (OSError, psutil.Error) as exc:
        result.errors.append(f"verify:{identity.pid}:{type(exc).__name__}:{exc}")
        return True
