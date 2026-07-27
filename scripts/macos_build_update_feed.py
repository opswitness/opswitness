#!/usr/bin/env python3
"""Build the signed Tauri Alpha update feed from final release assets."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--archive-url", required=True)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.archive_url.startswith("https://"):
        raise SystemExit("updater archive URL must use HTTPS")
    signature = args.signature.read_text(encoding="utf-8").strip()
    if not signature:
        raise SystemExit("updater signature is empty")
    epoch = os.getenv("SOURCE_DATE_EPOCH")
    published = (
        datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        if epoch
        else datetime.now(timezone.utc)
    )
    payload = {
        "version": args.version,
        "notes": "OpsWitness Community Alpha update. Review release notes before installing.",
        "pub_date": published.isoformat(),
        "platforms": {
            "darwin-aarch64": {
                "signature": signature,
                "url": args.archive_url,
            }
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
