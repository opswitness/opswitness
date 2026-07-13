"""Encrypted backup creation and isolated restore planning."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from quarterdeck.config import Settings, config_dir


def _postgres_env(database_url: str, *, database: str | None = None) -> dict[str, str]:
    parsed = urlparse(database_url)
    if parsed.scheme not in ("postgres", "postgresql") or not parsed.hostname:
        raise ValueError("database_url must be a PostgreSQL URL")
    env = dict(os.environ)
    env.update(
        {
            "PGHOST": parsed.hostname,
            "PGPORT": str(parsed.port or 5432),
            "PGDATABASE": database or parsed.path.lstrip("/"),
            "PGUSER": unquote(parsed.username or ""),
            "PGPASSWORD": unquote(parsed.password or ""),
        }
    )
    return env


def _backup_sources(settings: Settings) -> list[tuple[str, Path]]:
    return [
        ("paperclip", settings.services.paperclip_home.expanduser().resolve()),
        ("quarterdeck_state/ledger", settings.ledger_dir.expanduser().resolve()),
        ("quarterdeck_state/artifacts", (settings.ledger_dir.parent / "artifacts").resolve()),
        ("config", config_dir().resolve()),
    ]


def backup_plan(settings: Settings, output: Path | None = None) -> dict:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = (output or settings.backup.directory / f"quarterdeck-{stamp}.tar.age").expanduser().resolve()
    return {
        "mode": "create",
        "output": str(output),
        "recipient_configured": bool(settings.backup.age_recipient),
        "database_dump": "PostgreSQL custom format; password passed by environment only",
        "sources": [
            {"archive_path": archive, "path": str(path), "exists": path.exists()}
            for archive, path in _backup_sources(settings)
        ],
        "writes": [str(output)],
    }


def create_backup(settings: Settings, output: Path | None = None, *, execute: bool = False) -> dict:
    plan = backup_plan(settings, output)
    if not execute:
        return plan
    if not settings.database_url:
        raise ValueError("database_url is required for backup")
    if not settings.backup.age_recipient:
        raise ValueError("backup.age_recipient is required")
    output_path = Path(plan["output"])
    if output_path.parent.exists():
        mode = stat.S_IMODE(output_path.parent.stat().st_mode)
        if mode != 0o700:
            raise ValueError(
                f"backup directory mode must be 0700, found {mode:04o}: {output_path.parent}"
            )
    else:
        output_path.parent.mkdir(parents=True, mode=0o700)
    pg_dump = shutil.which("pg_dump")
    age = shutil.which("age")
    if not pg_dump or not age:
        raise ValueError("pg_dump and age must both be installed")
    partial_fd, partial_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.", suffix=".partial", dir=output_path.parent
    )
    partial = Path(partial_name)
    try:
        with tempfile.TemporaryDirectory(prefix="qd-backup-", dir=output_path.parent) as raw_tmp:
            tmp = Path(raw_tmp)
            os.chmod(tmp, 0o700)
            dump = tmp / "database.dump"
            subprocess.run(
                [pg_dump, "--format=custom", "--file", str(dump)],
                env=_postgres_env(settings.database_url),
                check=True,
            )
            manifest = tmp / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "created_at": datetime.now(UTC).isoformat(),
                        "components": ["database.dump", *[name for name, _ in _backup_sources(settings)]],
                    },
                    indent=2,
                )
            )
            os.chmod(manifest, 0o600)
            tar_path = tmp / "payload.tar"
            with tarfile.open(tar_path, "w") as archive:
                archive.add(dump, arcname="database.dump", recursive=False)
                archive.add(manifest, arcname="manifest.json", recursive=False)
                for archive_name, source in _backup_sources(settings):
                    if source.exists():
                        archive.add(source, arcname=archive_name)
            os.chmod(tar_path, 0o600)
            with os.fdopen(partial_fd, "wb") as encrypted:
                partial_fd = -1
                subprocess.run(
                    [age, "--recipient", settings.backup.age_recipient, str(tar_path)],
                    stdout=encrypted,
                    check=True,
                )
                encrypted.flush()
                os.fsync(encrypted.fileno())
        os.replace(partial, output_path)
        dir_fd = os.open(output_path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        plan["executed"] = True
        return plan
    finally:
        if partial_fd >= 0:
            os.close(partial_fd)
        try:
            partial.unlink()
        except FileNotFoundError:
            pass


def restore_plan(
    settings: Settings,
    archive: Path,
    identity: Path,
    target_root: Path,
    database_name: str,
    paperclip_port: int,
) -> dict:
    archive = archive.expanduser().resolve()
    identity = identity.expanduser().resolve()
    target_root = target_root.expanduser().resolve()
    protected = {
        config_dir().resolve(),
        settings.ledger_dir.parent.expanduser().resolve(),
        settings.services.paperclip_home.expanduser().resolve(),
    }
    if any(
        target_root == path
        or target_root.is_relative_to(path)
        or path.is_relative_to(target_root)
        for path in protected
    ):
        raise ValueError("restore target must be isolated from production paths")
    if paperclip_port in (3100, 5432) or not 1024 <= paperclip_port <= 65535:
        raise ValueError("restore Paperclip port must be an isolated non-production port")
    if not database_name.startswith("qd_restore_"):
        raise ValueError("restore database name must start with qd_restore_")
    return {
        "mode": "restore",
        "archive": str(archive),
        "identity": str(identity),
        "target_root": str(target_root),
        "database_name": database_name,
        "paperclip_port": paperclip_port,
        "writes": [str(target_root), f"postgres://.../{database_name}"],
        "next": "start Paperclip manually with restored paperclip/ dir, isolated DB, and this port",
    }


def restore_backup(
    settings: Settings,
    archive: Path,
    identity: Path,
    target_root: Path,
    database_name: str,
    paperclip_port: int,
    *,
    execute: bool = False,
) -> dict:
    plan = restore_plan(settings, archive, identity, target_root, database_name, paperclip_port)
    if not execute:
        return plan
    if not settings.database_url:
        raise ValueError("database_url is required for restore")
    if target_root.exists() and any(target_root.iterdir()):
        raise ValueError("restore target must not exist or must be empty")
    for tool in ("age", "createdb", "pg_restore"):
        if not shutil.which(tool):
            raise ValueError(f"{tool} must be installed")
    target_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(target_root, 0o700)
    with tempfile.TemporaryDirectory(prefix="qd-restore-") as raw_tmp:
        decrypted = Path(raw_tmp) / "payload.tar"
        subprocess.run(
            [shutil.which("age") or "age", "--decrypt", "--identity", str(identity), "--output", str(decrypted), str(archive)],
            check=True,
        )
        with tarfile.open(decrypted, "r") as tar:
            tar.extractall(target_root, filter="data")
    admin_env = _postgres_env(settings.database_url, database="postgres")
    subprocess.run([shutil.which("createdb") or "createdb", database_name], env=admin_env, check=True)
    restore_env = _postgres_env(settings.database_url, database=database_name)
    subprocess.run(
        [shutil.which("pg_restore") or "pg_restore", "--exit-on-error", str(target_root / "database.dump")],
        env=restore_env,
        check=True,
    )
    plan["executed"] = True
    return plan
