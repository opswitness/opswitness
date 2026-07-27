import os
import stat
from pathlib import Path

import pytest

from scripts import macos_canary_handoff as handoff


HOST_IDENTITY = "a" * 64


def _permission_field(path: Path) -> str:
    metadata = path.lstat()
    return stat.filemode(metadata.st_mode)


def _fixture(tmp_path: Path, monkeypatch):
    shared = tmp_path / "Shared"
    shared.mkdir(mode=0o777)
    shared.chmod(0o1777)
    identity_root = tmp_path / "Identity"
    identity_root.mkdir(mode=0o755)
    identity = identity_root / "host-identity.sha256"
    identity.write_text(f"{HOST_IDENTITY}\n", encoding="ascii")
    identity.chmod(0o444)
    monkeypatch.setattr(handoff, "_permission_field", _permission_field)
    return shared, shared / "OpsWitnessAlphaCanary", identity


def _prepare(shared, root, identity, **overrides):
    parameters = {
        "shared_root": shared,
        "handoff_root": root,
        "identity_file": identity,
        "expected_host_identity_sha256": HOST_IDENTITY,
        "run_id": 123,
        "run_attempt": 2,
        "runner_uid": os.getuid(),
        "shared_uid": os.getuid(),
        "shared_gid": os.getgid(),
        "identity_uid": os.getuid(),
    }
    parameters.update(overrides)
    return handoff.prepare_handoff(**parameters)


def test_prepare_handoff_creates_only_private_runner_owned_directories(
    tmp_path,
    monkeypatch,
):
    shared, root, identity = _fixture(tmp_path, monkeypatch)

    run_root = _prepare(shared, root, identity)

    assert run_root == root / "runs" / "123-2"
    for path in (root, root / "requests", root / "runs", run_root):
        metadata = path.lstat()
        assert stat.S_ISDIR(metadata.st_mode)
        assert metadata.st_uid == os.getuid()
        assert stat.S_IMODE(metadata.st_mode) == 0o700


def test_prepare_handoff_rejects_precreated_world_writable_root(
    tmp_path,
    monkeypatch,
):
    shared, root, identity = _fixture(tmp_path, monkeypatch)
    root.mkdir(mode=0o777)

    with pytest.raises(handoff.HandoffError, match="unsafe permissions"):
        _prepare(shared, root, identity)


def test_secure_directory_rejects_wrong_owner_and_symlink(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    monkeypatch.setattr(handoff, "_permission_field", _permission_field)
    with pytest.raises(handoff.HandoffError, match="unexpected owner"):
        handoff._validate_directory(
            target,
            expected_uid=os.getuid() + 1,
            expected_gid=None,
            expected_mode=0o700,
        )

    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(handoff.HandoffError, match="real directory"):
        handoff._validate_directory(
            link,
            expected_uid=os.getuid(),
            expected_gid=None,
            expected_mode=0o700,
        )


def test_secure_directory_rejects_acl_marker(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    monkeypatch.setattr(
        handoff,
        "_permission_field",
        lambda _path: "drwx------+",
    )

    with pytest.raises(handoff.HandoffError, match="ACL"):
        handoff._validate_directory(
            target,
            expected_uid=os.getuid(),
            expected_gid=None,
            expected_mode=0o700,
        )


def test_secure_directory_allows_non_authorizing_xattr_marker(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    monkeypatch.setattr(
        handoff,
        "_permission_field",
        lambda _path: "drwx------@",
    )

    handoff._validate_directory(
        target,
        expected_uid=os.getuid(),
        expected_gid=None,
        expected_mode=0o700,
    )


def test_prepare_handoff_rejects_unapproved_host_identity(tmp_path, monkeypatch):
    shared, root, identity = _fixture(tmp_path, monkeypatch)

    with pytest.raises(handoff.HandoffError, match="protected value"):
        _prepare(
            shared,
            root,
            identity,
            expected_host_identity_sha256="b" * 64,
        )
