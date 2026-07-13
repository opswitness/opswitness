#!/usr/bin/env python3
"""Fail when a non-merge commit lacks a Developer Certificate signoff."""

import re
import subprocess
import sys


SIGNOFF = re.compile(r"^Signed-off-by:\s+.+\s+<[^<>]+>$", re.IGNORECASE | re.MULTILINE)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else ""
    head = sys.argv[2] if len(sys.argv) > 2 else "HEAD"
    if not base or set(base) == {"0"}:
        commits = git("rev-list", head).splitlines()
    else:
        commits = git("rev-list", f"{base}..{head}").splitlines()
    missing: list[str] = []
    for commit in commits:
        parents = git("show", "-s", "--format=%P", commit).split()
        if len(parents) > 1:
            continue
        message = git("show", "-s", "--format=%B", commit)
        if not SIGNOFF.search(message):
            missing.append(commit)
    if missing:
        print("Commits missing Signed-off-by:", *missing, sep="\n  ", file=sys.stderr)
        return 1
    print(f"DCO verified for {len(commits)} commit(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
