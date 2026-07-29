#!/usr/bin/env python3
"""Create and verify the complete desktop runtime file inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import stat
from pathlib import Path


PAPERCLIP_STAGING_EXCLUSIONS = [
    "paperclip/node_modules/@agentclientprotocol/claude-agent-acp",
    "paperclip/node_modules/@anthropic-ai/claude-agent-sdk-darwin-arm64",
]
PAPERCLIP_ENTRYPOINT_SHA256 = (
    "070df2f71906daac276da1c90404fd11463c4992f78f5d43fee69d6036d61252"
)
PAPERCLIP_STAGING_TREES = {
    PAPERCLIP_STAGING_EXCLUSIONS[0]: {
        "sha256": "804a73195127da096a64a3a607890e92d3180d7e79f92c8b8438cc2786909c44",
        "file_count": 757,
        "symlink_count": 0,
        "total_bytes": 8_526_606,
    },
    PAPERCLIP_STAGING_EXCLUSIONS[1]: {
        "sha256": "65910ea7797a768278c01ded9c16369ba0f7f06050cf96bfa0d3f09d2a018b88",
        "file_count": 4,
        "symlink_count": 0,
        "total_bytes": 219_856_632,
    },
}
PAPERCLIP_STAGING_MARKERS = {
    PAPERCLIP_STAGING_EXCLUSIONS[0]: [
        {
            "path": f"{PAPERCLIP_STAGING_EXCLUSIONS[0]}/package.json",
            "sha256": "f3f714ec0caf56a571662fdc0d9b653c98be34ad4ea0ab09f0f67c22bd421d6c",
            "size": 2_194,
        },
        {
            "path": f"{PAPERCLIP_STAGING_EXCLUSIONS[0]}/dist/index.js",
            "sha256": "5d946f0d74a75ce418796b5c232a844b96a6c6c902c45dfc73027634d48ee273",
            "size": 2_972,
        },
        {
            "path": (
                f"{PAPERCLIP_STAGING_EXCLUSIONS[0]}/node_modules/"
                "@anthropic-ai/claude-agent-sdk/package.json"
            ),
            "sha256": "1c5d0b2ca32a2fe1349543120d21fe64eb82e340305381be37dfc88d5964bb62",
            "size": 2_380,
        },
    ],
    PAPERCLIP_STAGING_EXCLUSIONS[1]: [
        {
            "path": f"{PAPERCLIP_STAGING_EXCLUSIONS[1]}/package.json",
            "sha256": "f9e2f053b8ed6e31d7cfe3076fc7add848d0a6bb0e24bb3ace0935a0143a87de",
            "size": 274,
        },
        {
            "path": f"{PAPERCLIP_STAGING_EXCLUSIONS[1]}/LICENSE.md",
            "sha256": "8ce94b9478bb9868f9641f818e06cd722fbe55d4c22e2d2ed11971b20146173a",
            "size": 147,
        },
        {
            "path": f"{PAPERCLIP_STAGING_EXCLUSIONS[1]}/claude",
            "sha256": "252307a7413de6e151ef91168903a4f5bf1159296b0e71d1cb7ae2e74ff18e9a",
            "size": 219_856_048,
        },
    ],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock(path: Path, *, release: bool) -> dict:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != 1:
        raise SystemExit("unsupported vendor-lock schema")
    if payload.get("target") != "aarch64-apple-darwin":
        raise SystemExit("vendor-lock target must be aarch64-apple-darwin")
    components = payload.get("components")
    if not isinstance(components, list) or not components:
        raise SystemExit("vendor-lock must contain components")
    identifiers: set[str] = set()
    for component in components:
        identifier = component.get("id")
        if not isinstance(identifier, str) or identifier in identifiers:
            raise SystemExit(f"invalid or duplicate vendor component: {identifier!r}")
        identifiers.add(identifier)
        entrypoints = component.get("entrypoints")
        if not isinstance(entrypoints, list) or not entrypoints:
            raise SystemExit(f"{identifier}: entrypoints are required")
        if release:
            approved = component.get("redistribution_review") == "approved"
            if identifier == "opswitness-backend":
                complete = (
                    isinstance(component.get("build_source_commit"), str)
                    and isinstance(component.get("build_artifact_sha256"), str)
                )
            else:
                complete = isinstance(component.get("upstream_sha256"), str)
            if not approved or not complete:
                raise SystemExit(f"{identifier}: redistribution lock is incomplete")
    return payload


def _lexical_symlink_destination(relative_link: Path, target: Path) -> Path:
    """Resolve ``target`` lexically without allowing it to leave the payload."""

    parts: list[str] = []
    for part in (*relative_link.parent.parts, *target.parts):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError("target escapes the runtime payload")
            parts.pop()
            continue
        parts.append(part)
    return Path(*parts)


def validate_symlink(runtime: Path, link: Path, target_text: str) -> None:
    """Require a relative, contained, and currently resolvable symlink target."""

    if not target_text:
        raise ValueError("target is empty")
    target = Path(target_text)
    if target.is_absolute():
        raise ValueError("target must be relative")
    relative_link = link.relative_to(runtime)
    _lexical_symlink_destination(relative_link, target)
    try:
        resolved = (link.parent / target).resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"target is broken: {exc}") from exc
    try:
        resolved.relative_to(runtime)
    except ValueError as exc:
        raise ValueError("target resolves outside the runtime payload") from exc


def resource_entries(runtime: Path) -> tuple[list[dict[str, object]], set[str]]:
    """Inventory regular files and safe symlinks without following link directories."""

    runtime = runtime.resolve(strict=True)
    files: list[dict[str, object]] = []
    discovered: set[str] = set()
    candidates: list[Path] = []
    for directory, directory_names, file_names in os.walk(runtime, followlinks=False):
        directory_path = Path(directory)
        candidates.extend(directory_path / name for name in directory_names)
        candidates.extend(directory_path / name for name in file_names)

    for path in sorted(candidates, key=lambda candidate: candidate.relative_to(runtime).as_posix()):
        if path.name in {".gitkeep", "resource-manifest.json"}:
            if path.is_symlink():
                raise SystemExit(f"reserved runtime resource must not be a symlink: {path}")
            continue
        relative = path.relative_to(runtime).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            try:
                validate_symlink(runtime, path, target)
            except ValueError as exc:
                raise SystemExit(f"unsafe runtime resource symlink {path}: {exc}") from exc
            discovered.add(relative)
            files.append(
                {
                    "path": relative,
                    "kind": "symlink",
                    "target": target,
                }
            )
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            raise SystemExit(f"unsupported runtime resource type: {path}")
        discovered.add(relative)
        mode = stat.S_IMODE(path.stat().st_mode)
        files.append(
            {
                "path": relative,
                "kind": "file",
                "sha256": sha256(path),
                "size": path.stat().st_size,
                "executable": bool(mode & 0o111),
            }
        )
    return files, discovered


def validate_architecture_provenance(
    provenance: dict, discovered: set[str]
) -> None:
    """Require a complete, auditable architecture-normalization record."""

    if (
        provenance.get("schema_version") != 1
        or provenance.get("target_architecture") != "arm64"
        or not isinstance(provenance.get("entries"), list)
    ):
        raise SystemExit("invalid macOS architecture normalization provenance")
    for entry in provenance["entries"]:
        if not isinstance(entry, dict):
            raise SystemExit("invalid macOS architecture normalization provenance")
        path = entry.get("path")
        before_archs = entry.get("before_archs")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(before_archs, list)
            or not before_archs
            or not isinstance(entry.get("before_sha256"), str)
        ):
            raise SystemExit("invalid macOS architecture normalization provenance")
        action = entry.get("action")
        if action == "excluded_non_arm_vendor_prebuild":
            if (
                entry.get("after_archs") != []
                or entry.get("after_sha256") is not None
                or path in discovered
            ):
                raise SystemExit("invalid macOS architecture normalization exclusion")
            continue
        if action not in {"preserved", "thinned_to_arm64"}:
            raise SystemExit("invalid macOS architecture normalization provenance")
        if (
            entry.get("after_archs") != ["arm64"]
            or not isinstance(entry.get("after_sha256"), str)
            or path not in discovered
        ):
            raise SystemExit("invalid macOS architecture normalization provenance")


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_aioncore_staging_filter(
    component: dict,
    runtime: Path,
    files: list[dict[str, object]],
    discovered: set[str],
) -> dict[str, object]:
    """Bind the AionCore Codex-only transform to the final inventory."""

    policy = component["staging_filter"]
    if (
        component.get("id") != "aioncore"
        or component.get("version") != "0.1.45"
        or policy.get("profile") != "codex-only"
        or policy.get("applies_to_version") != "0.1.45"
    ):
        raise SystemExit("unsupported AionCore staging filter profile")
    exclusions = policy.get("source_exclusions")
    shim_root = policy.get("compatibility_shim_root")
    receipt_path = policy.get("receipt")
    if (
        not isinstance(exclusions, list)
        or not exclusions
        or not all(isinstance(path, str) and path for path in exclusions)
        or not isinstance(shim_root, str)
        or not shim_root
        or not isinstance(receipt_path, str)
        or not receipt_path
    ):
        raise SystemExit("invalid AionCore staging filter policy")

    by_path = {
        entry["path"]: entry
        for entry in files
        if isinstance(entry.get("path"), str)
    }
    receipt_entry = by_path.get(receipt_path)
    if receipt_entry is None or receipt_entry.get("kind") != "file":
        raise SystemExit("missing Codex-only staging exclusion receipt")
    try:
        receipt = json.loads((runtime / receipt_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("invalid Codex-only staging exclusion receipt") from exc
    if (
        receipt.get("schema_version") != 1
        or receipt.get("profile") != "codex-only"
        or receipt.get("component") != "aioncore"
        or receipt.get("policy", {}).get("profile") != "codex-only"
        or receipt.get("policy", {}).get("applies_to_version") != "0.1.45"
        or receipt.get("policy", {}).get("receipt") != receipt_path
    ):
        raise SystemExit("invalid Codex-only staging exclusion receipt")
    source_entries = receipt.get("source_exclusions")
    if (
        not isinstance(source_entries, list)
        or [entry.get("path") for entry in source_entries if isinstance(entry, dict)]
        != exclusions
        or not all(
            isinstance(entry, dict)
            and entry.get("original_source_tree_removed") is True
            and isinstance(entry.get("original_tree"), dict)
            and _valid_sha256(entry["original_tree"].get("sha256"))
            and isinstance(entry["original_tree"].get("file_count"), int)
            and entry["original_tree"]["file_count"] > 0
            and isinstance(entry.get("original_markers"), list)
            and len(entry["original_markers"]) >= 3
            and all(
                isinstance(marker, dict)
                and isinstance(marker.get("path"), str)
                and marker["path"].startswith(f"{entry['path']}/")
                and _valid_sha256(marker.get("sha256"))
                and isinstance(marker.get("size"), int)
                and marker["size"] > 0
                for marker in entry["original_markers"]
            )
            for entry in source_entries
        )
    ):
        raise SystemExit("Codex-only source exclusion receipt does not match vendor policy")

    shim = receipt.get("generated_compatibility_shim")
    generated = shim.get("files") if isinstance(shim, dict) else None
    if (
        not isinstance(shim, dict)
        or shim.get("root") != shim_root
        or not isinstance(generated, list)
        or not generated
    ):
        raise SystemExit("invalid Codex-only compatibility shim receipt")
    generated_paths: set[str] = set()
    for expected in generated:
        if not isinstance(expected, dict):
            raise SystemExit("invalid Codex-only compatibility shim receipt")
        path = expected.get("path")
        if (
            not isinstance(path, str)
            or not path.startswith(f"{shim_root}/")
            or path in generated_paths
            or not _valid_sha256(expected.get("sha256"))
            or not isinstance(expected.get("size"), int)
            or expected["size"] < 0
            or not isinstance(expected.get("executable"), bool)
        ):
            raise SystemExit("invalid Codex-only compatibility shim receipt")
        generated_paths.add(path)
        observed = by_path.get(path)
        if (
            observed is None
            or observed.get("kind") != "file"
            or observed.get("sha256") != expected["sha256"]
            or observed.get("size") != expected["size"]
            or observed.get("executable") != expected["executable"]
        ):
            raise SystemExit(f"Codex-only compatibility shim mismatch: {path}")
    observed_shim_paths = {
        path for path in discovered if path.startswith(f"{shim_root}/")
    }
    if observed_shim_paths != generated_paths:
        raise SystemExit("Codex-only compatibility shim contains unrecorded files")

    scan = receipt.get("proprietary_path_scan")
    if (
        not isinstance(scan, dict)
        or scan.get("forbidden_matches") != []
        or scan.get("allowed_first_party_shim_path") not in generated_paths
        or not _valid_sha256(scan.get("allowed_first_party_shim_sha256"))
        or by_path[scan["allowed_first_party_shim_path"]].get("sha256")
        != scan["allowed_first_party_shim_sha256"]
    ):
        raise SystemExit("invalid proprietary-path scan in staging receipt")
    for path in discovered:
        if not path.startswith("aioncore/managed-resources/"):
            continue
        parts = Path(path).parts
        names_anthropic_payload = (
            "@anthropic-ai" in parts
            or "claude-agent-acp" in parts
            or Path(path).name in {"anthropic-ai-sdk", "claude-agent-acp"}
        )
        if (
            names_anthropic_payload
            and path != scan["allowed_first_party_shim_path"]
            and not path.startswith(f"{shim_root}/")
        ):
            raise SystemExit(f"unfiltered Anthropic managed-resource path remains: {path}")

    audit = receipt.get("aioncore_manifest_audit")
    if (
        not isinstance(audit, dict)
        or audit.get("path") != "aioncore/manifest.json"
        or audit.get("rewrite_required") is not False
        or not _valid_sha256(audit.get("sha256"))
        or by_path.get("aioncore/manifest.json", {}).get("sha256") != audit["sha256"]
    ):
        raise SystemExit("invalid AionCore manifest audit in staging receipt")
    after = receipt.get(
        "managed_resources_after_filter_before_architecture_normalization"
    )
    if (
        not isinstance(after, dict)
        or not _valid_sha256(after.get("sha256"))
        or not isinstance(after.get("file_count"), int)
        or after["file_count"] <= 0
    ):
        raise SystemExit("invalid post-filter managed-resource digest in staging receipt")
    return {
        "profile": "codex-only",
        "receipt": {
            "path": receipt_path,
            "sha256": receipt_entry["sha256"],
        },
        "source_exclusions": exclusions,
        "compatibility_shim_root": shim_root,
        "upstream_source_tree_removed": True,
    }


def _validate_paperclip_staging_filter(
    component: dict,
    runtime: Path,
    files: list[dict[str, object]],
    discovered: set[str],
) -> dict[str, object]:
    """Bind Paperclip's exact proprietary-runtime removal receipt."""

    policy = component["staging_filter"]
    expected_exclusions = PAPERCLIP_STAGING_EXCLUSIONS
    if (
        component.get("id") != "paperclip"
        or component.get("version") != "2026.707.0"
        or policy.get("profile") != "codex-only"
        or policy.get("applies_to_version") != "2026.707.0"
        or policy.get("source_exclusions") != expected_exclusions
        or policy.get("compatibility_shim_root") is not None
        or policy.get("receipt") != "paperclip-staging-exclusions.json"
    ):
        raise SystemExit("unsupported Paperclip staging filter profile")

    by_path = {
        entry["path"]: entry
        for entry in files
        if isinstance(entry.get("path"), str)
    }
    receipt_path = policy["receipt"]
    receipt_entry = by_path.get(receipt_path)
    if receipt_entry is None or receipt_entry.get("kind") != "file":
        raise SystemExit("missing Paperclip Codex-only staging exclusion receipt")
    try:
        receipt = json.loads((runtime / receipt_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "invalid Paperclip Codex-only staging exclusion receipt"
        ) from exc
    if (
        receipt.get("schema_version") != 1
        or receipt.get("profile") != "codex-only"
        or receipt.get("component") != "paperclip"
        or receipt.get("reason")
        != "upstream_anthropic_redistribution_not_approved"
        or receipt.get("locked_paperclip_entrypoint")
        != {
            "path": "paperclip/dist/index.js",
            "sha256": PAPERCLIP_ENTRYPOINT_SHA256,
        }
        or by_path.get("paperclip/dist/index.js", {}).get("sha256")
        != PAPERCLIP_ENTRYPOINT_SHA256
        or receipt.get("policy")
        != {
            "profile": "codex-only",
            "applies_to_version": "2026.707.0",
            "source_exclusions": expected_exclusions,
            "receipt": receipt_path,
        }
    ):
        raise SystemExit("invalid Paperclip Codex-only staging exclusion receipt")

    source_entries = receipt.get("source_exclusions")
    if (
        not isinstance(source_entries, list)
        or len(source_entries) != len(expected_exclusions)
        or [entry.get("path") for entry in source_entries if isinstance(entry, dict)]
        != expected_exclusions
    ):
        raise SystemExit(
            "Paperclip source exclusion receipt does not match vendor policy"
        )
    for entry in source_entries:
        path = entry.get("path") if isinstance(entry, dict) else None
        if (
            not isinstance(entry, dict)
            or path not in PAPERCLIP_STAGING_TREES
            or entry.get("original_source_tree_removed") is not True
            or entry.get("original_tree") != PAPERCLIP_STAGING_TREES[path]
            or entry.get("original_markers") != PAPERCLIP_STAGING_MARKERS[path]
        ):
            raise SystemExit("invalid locked Paperclip source exclusion receipt")

    if receipt.get("removed_companion_links") != [
        {
            "path": "paperclip/node_modules/.bin/claude-agent-acp",
            "target": "../@agentclientprotocol/claude-agent-acp/dist/index.js",
        }
    ]:
        raise SystemExit("invalid Paperclip Claude ACP companion-link receipt")
    if receipt.get("proprietary_path_scan") != {"forbidden_matches": []}:
        raise SystemExit("invalid Paperclip proprietary-path scan")
    for path in discovered:
        if not path.startswith("paperclip/"):
            continue
        if (
            "claude-agent-sdk" in path
            or "@agentclientprotocol/claude-agent-acp" in path
            or path == "paperclip/node_modules/.bin/claude-agent-acp"
        ):
            raise SystemExit(f"unfiltered Paperclip Anthropic payload remains: {path}")

    after = receipt.get(
        "paperclip_after_filter_before_architecture_normalization"
    )
    if (
        not isinstance(after, dict)
        or not _valid_sha256(after.get("sha256"))
        or not isinstance(after.get("file_count"), int)
        or after["file_count"] <= 0
        or not isinstance(after.get("symlink_count"), int)
        or after["symlink_count"] < 0
        or not isinstance(after.get("total_bytes"), int)
        or after["total_bytes"] <= 0
    ):
        raise SystemExit("invalid post-filter Paperclip digest in staging receipt")
    return {
        "profile": "codex-only",
        "receipt": {
            "path": receipt_path,
            "sha256": receipt_entry["sha256"],
        },
        "source_exclusions": expected_exclusions,
        "removed_companion_links": [
            "paperclip/node_modules/.bin/claude-agent-acp"
        ],
        "upstream_source_tree_removed": True,
    }


def validate_staging_filter(
    vendor: dict,
    runtime: Path,
    files: list[dict[str, object]],
    discovered: set[str],
) -> dict[str, object] | None:
    """Bind every vendor-locked Codex-only transform to the final inventory."""

    configured = [
        component
        for component in vendor["components"]
        if isinstance(component.get("staging_filter"), dict)
    ]
    if not configured:
        return None
    by_identifier = {component.get("id"): component for component in configured}
    if len(by_identifier) != len(configured) or not set(by_identifier).issubset(
        {"aioncore", "paperclip"}
    ):
        raise SystemExit("unsupported or duplicate Codex-only staging filter")

    summaries: dict[str, dict[str, object]] = {}
    if "aioncore" in by_identifier:
        summaries["aioncore"] = _validate_aioncore_staging_filter(
            by_identifier["aioncore"], runtime, files, discovered
        )
    if "paperclip" in by_identifier:
        summaries["paperclip"] = _validate_paperclip_staging_filter(
            by_identifier["paperclip"], runtime, files, discovered
        )
    if len(summaries) == 1:
        return next(iter(summaries.values()))
    return {
        "profile": "codex-only",
        "components": summaries,
        "upstream_proprietary_payloads_removed": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--vendor-lock", required=True, type=Path)
    parser.add_argument("--mode", choices=("adhoc", "release"), default="adhoc")
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument(
        "--verify-existing",
        action="store_true",
        help="verify the staged manifest before any nested code signature changes",
    )
    phase.add_argument(
        "--post-sign",
        action="store_true",
        help="refresh hashes after nested signing and before the outer app is signed",
    )
    parser.add_argument(
        "--pre-sign-manifest-sha256",
        help="required staged-manifest digest that binds a post-sign refresh",
    )
    args = parser.parse_args()

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("runtime staging requires native macOS arm64")
    pre_sign_manifest_sha256 = args.pre_sign_manifest_sha256
    if args.post_sign:
        if (
            not isinstance(pre_sign_manifest_sha256, str)
            or len(pre_sign_manifest_sha256) != 64
            or any(character not in "0123456789abcdef" for character in pre_sign_manifest_sha256)
        ):
            raise SystemExit(
                "post-sign manifest refresh requires a lowercase staged-manifest SHA-256"
            )
    elif pre_sign_manifest_sha256 is not None:
        raise SystemExit("--pre-sign-manifest-sha256 requires --post-sign")

    vendor = load_lock(args.vendor_lock, release=args.mode == "release")
    expected_entrypoints = {
        entrypoint
        for component in vendor["components"]
        for entrypoint in component["entrypoints"]
    }
    files, discovered = resource_entries(args.runtime)

    provenance_path = "architecture-provenance.json"
    provenance_entry = next(
        (entry for entry in files if entry["path"] == provenance_path), None
    )
    if provenance_entry is None or provenance_entry.get("kind") != "file":
        raise SystemExit("missing macOS architecture normalization provenance")
    try:
        provenance = json.loads((args.runtime / provenance_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit("invalid macOS architecture normalization provenance") from exc
    validate_architecture_provenance(provenance, discovered)
    staging_filter = validate_staging_filter(
        vendor,
        args.runtime,
        files,
        discovered,
    )

    missing = expected_entrypoints - discovered
    if missing:
        raise SystemExit(f"missing vendor entrypoints: {sorted(missing)}")
    for component in vendor["components"]:
        for prefix in component.get("required_prefixes", []):
            if not any(path.startswith(prefix) for path in discovered):
                raise SystemExit(
                    f"{component['id']}: required resource prefix is empty: {prefix}"
                )
    if args.mode == "release" and not args.post_sign:
        backend = next(
            component
            for component in vendor["components"]
            if component["id"] == "opswitness-backend"
        )
        backend_path = args.runtime / backend["entrypoints"][0]
        if sha256(backend_path) != backend["build_artifact_sha256"]:
            raise SystemExit("opswitness-backend build artifact digest does not match resolved lock")
    manifest = {
        "schema_version": 2,
        "target": "aarch64-apple-darwin",
        "distribution_mode": args.mode,
        "integrity_phase": "post-sign" if args.post_sign else "staged",
        "architecture_normalization": {
            "path": provenance_path,
            "sha256": provenance_entry["sha256"],
        },
        "files": files,
    }
    if staging_filter is not None:
        manifest["staging_filter"] = staging_filter
    if args.post_sign:
        manifest["pre_sign_manifest_sha256"] = pre_sign_manifest_sha256
    destination = args.runtime / "resource-manifest.json"
    if args.verify_existing:
        try:
            existing = json.loads(destination.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit("missing or invalid staged runtime resource manifest") from exc
        if existing != manifest:
            raise SystemExit("staged runtime resource manifest does not match current payload")
        return
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, destination)
    os.chmod(destination, 0o644)


if __name__ == "__main__":
    main()
