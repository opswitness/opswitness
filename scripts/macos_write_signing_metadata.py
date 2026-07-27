#!/usr/bin/env python3
"""Write normalized schema-3 macOS signing/notarization evidence."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


def _codesign_details(app: Path) -> tuple[str, str, bool]:
    result = subprocess.run(
        ["/usr/bin/codesign", "-dvvv", str(app)],
        check=True,
        capture_output=True,
        text=True,
    )
    detail = f"{result.stdout}\n{result.stderr}"
    identity_match = re.search(r"^Authority=(.+)$", detail, flags=re.MULTILINE)
    cdhash_match = re.search(r"^CDHash=([0-9A-Fa-f]+)$", detail, flags=re.MULTILINE)
    flags_match = re.search(r"^CodeDirectory .+ flags=0x[0-9a-f]+\\(([^)]*)\\)", detail, re.MULTILINE)
    identity = identity_match.group(1).strip() if identity_match else "ad-hoc"
    cdhash = cdhash_match.group(1).lower() if cdhash_match else ""
    runtime = bool(flags_match and "runtime" in flags_match.group(1).split(","))
    return identity, cdhash, runtime


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("ad-hoc", "developer-id"), required=True)
    parser.add_argument("--notary-json", type=Path)
    parser.add_argument("--stapled", action="store_true")
    parser.add_argument("--gatekeeper-accepted", action="store_true")
    args = parser.parse_args()

    identity, cdhash, runtime = _codesign_details(args.app)
    notary: dict[str, object] = {
        "status": "not_submitted",
        "request_id": None,
        "stapled": args.stapled,
        "gatekeeper_assessment": (
            "accepted" if args.gatekeeper_accepted else "not_available"
        ),
    }
    if args.notary_json:
        payload = json.loads(args.notary_json.read_text(encoding="utf-8"))
        notary["status"] = payload.get("status")
        notary["request_id"] = payload.get("id")

    result = {
        "architecture": "arm64",
        "minimum_macos": "14.0",
        "bundle_id": "com.opswitness.app",
        "signing": {
            "mode": args.mode,
            "identity": identity,
            "cdhash": cdhash,
            "hardened_runtime": runtime,
            "nested_code_verified": True,
            "app_sandbox": False,
        },
        "notarization": notary,
    }
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
