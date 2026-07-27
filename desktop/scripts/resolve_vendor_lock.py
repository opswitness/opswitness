#!/usr/bin/env python3
"""Create the ephemeral lock bundled into a desktop build."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--mode", choices=("adhoc", "release"), default="adhoc")
    parser.add_argument("--commit")
    args = parser.parse_args()

    payload = json.loads(args.source.read_text())
    backend = next(
        component
        for component in payload["components"]
        if component["id"] == "opswitness-backend"
    )
    commit = args.commit
    if args.mode == "release":
        if not commit or not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise SystemExit("release lock requires --commit with the exact 40-hex release commit")
        backend["build_source_commit"] = commit
        backend["build_artifact_sha256"] = sha256(args.backend)
        backend["redistribution_review"] = "approved"
        backend["notice"] = (
            "Built from the exact release commit; build_source_commit and "
            "build_artifact_sha256 bind this first-party artifact."
        )
    else:
        backend["build_source_commit"] = None
        backend["build_artifact_sha256"] = sha256(args.backend)

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.destination)
    os.chmod(args.destination, 0o644)


if __name__ == "__main__":
    main()
