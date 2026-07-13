#!/usr/bin/env python3
"""Create release hashes and a small provenance manifest for distribution files."""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    files = sorted([*dist.glob("*.whl"), *dist.glob("*.tar.gz")])
    if not files:
        print(f"no distributions under {dist}", file=sys.stderr)
        return 2
    records = [{"name": path.name, "sha256": sha256(path), "size": path.stat().st_size} for path in files]
    (dist / "SHA256SUMS").write_text(
        "".join(f"{record['sha256']}  {record['name']}\n" for record in records)
    )
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "python": sys.version.split()[0],
        "artifacts": records,
    }
    (dist / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
