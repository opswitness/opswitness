"""qd init v2 — discover, classify, and generate CANDIDATES; enrollment is a human act.

Product doctrine (review-hardened):
- Auto-discover, auto-generate candidates; a job is monitored only after one explicit
  human confirmation. Auto-tighten may later run unattended (bounded, audited,
  rollbackable); auto-loosen is propose-only, always.
- Canonical ID = the full launchd label. Short names are display sugar and may collide
  (real machines have two `gateway`s); collisions are reported, never silently dropped.
- Two files: `schedules.generated.yaml` is machine-owned and rebuilt atomically on every
  init; `schedules.yaml` is user-owned and NEVER rewritten by qd — runtime merges the two.
- Classification is three-way: interval / calendar / service. A KeepAlive login item is
  not a "calendar job"; it is an unscheduled service and is never auto-enrolled.
- Zero external services and zero initial configuration required — not "zero
  dependencies" (Python/Typer/Pydantic/PyYAML are real).

Grace learning (v-next, recorded here so we don't re-derive it wrong): learn from the
distribution of (scheduled fire time → observed run_started) delays, NOT from run
durations — watchdog already anchors on last-event time, so duration-based grace would
double-count runtime. Newly observed periodic jobs become candidates, not monitors.
"""

import fcntl
import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from opswitness.adopt import job_name_from_label, scan
from opswitness.fsutil import atomic_write
from opswitness.schedules import classify_schedule


class ScheduleOverride(BaseModel):
    """Whitelist of user-overridable schedule fields. Identity fields (job/label/
    class/calendar/interval) are NOT overridable — the canonical ID and discovered
    facts belong to the ledger and the plists, not to config."""

    model_config = ConfigDict(extra="forbid")
    grace_seconds: int | None = Field(default=None, gt=0)
    enabled: bool | None = None


class UserSchedulesConfig(BaseModel):
    """Strict schema for the user-owned schedules.yaml. Unknown fields and scalar
    `enroll` values are rejected loudly — a trust system never guesses config."""

    model_config = ConfigDict(extra="forbid")
    enroll: list[str] = []
    overrides: dict[str, ScheduleOverride] = {}


class LegacyScheduleEntry(BaseModel):
    """Strict schema for explicit --schedules files ({jobs: [...]})."""

    model_config = ConfigDict(extra="forbid")
    job: str
    label: str | None = None
    display_name: str | None = None
    expected_interval_seconds: int | None = Field(default=None, gt=0)
    grace_seconds: int = Field(default=300, gt=0)
    enabled: bool = True
    note: str | None = None
    source: str | None = None


class LegacySchedulesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobs: list[LegacyScheduleEntry] = []


def load_legacy_schedules(path: Path) -> list[dict[str, Any]]:
    """Unified validator for explicit --schedules files. Empty file = valid-empty
    (=> no coverage downstream); every malformation raises ValueError loudly."""
    if not path.exists():
        raise ValueError(f"{path}: schedules file not found")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML — {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    if "retired" in raw:
        raise ValueError(
            f"{path}: `retired:` was removed; use `qd retire JOB --reason ...` "
            "so retirement remains in the append-only ledger"
        )
    try:
        parsed = LegacySchedulesFile.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{path}: schema violation — {exc}") from exc
    return [e.model_dump(exclude_none=True) for e in parsed.jobs]

GENERATED_NAME = "schedules.generated.yaml"
USER_NAME = "schedules.yaml"

DEFAULT_CONFIG = """\
# OpsWitness config (created by `qd init` — safe to edit, init never overwrites)
# paperclip:
#   api_base: http://127.0.0.1:3100
#   company_id: <set after Paperclip install>
# ledger_dir: ~/.local/state/opswitness/ledger
# redact: true
"""

USER_TEMPLATE = """\
# OpsWitness user overrides — qd NEVER rewrites this file.
# Enroll candidates from schedules.generated.yaml by label (exact or glob):
enroll: []
#  - "com.tianyuzhou.*"
#  - "com.example.one-job"
# Per-label overrides (merged over generated values):
# overrides:
#   com.tianyuzhou.feed-monitor:
#     grace_seconds: 120
"""


def default_grace(interval: int) -> int:
    return max(300, interval // 5)


def classify_source(entry: dict[str, Any]) -> str:
    if "expected_interval_seconds" in entry:
        return "interval"
    if "calendar" in entry:
        return "calendar"
    return "service"


def build_generated(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure discovery facts keyed by full label. No user state lives here."""
    by_label: dict[str, dict[str, Any]] = {}
    short_names: dict[str, list[str]] = {}
    errors: list[dict[str, str]] = []
    for e in entries:
        if "error" in e:
            errors.append({"path": e.get("path", "?"), "error": e["error"]})
            continue
        label = e["label"]
        cls = classify_source(e)
        item: dict[str, Any] = {
            "label": label,
            "class": cls,
            "command_root": (e.get("command") or ["?"])[0],
            "wrapped": e.get("wrapped", False),
        }
        if cls == "interval":
            item["expected_interval_seconds"] = e["expected_interval_seconds"]
            item["grace_seconds"] = default_grace(e["expected_interval_seconds"])
        elif cls == "calendar":
            item["calendar"] = e.get("calendar")  # structured, not stringified —
            # the future calendar watchdog must not have to re-parse a repr()
        try:
            item["source_hash"] = "sha256:" + hashlib.sha256(
                Path(e["path"]).read_bytes()
            ).hexdigest()[:16]
        except OSError:
            pass
        by_label[label] = item
        short_names.setdefault(job_name_from_label(label), []).append(label)

    collisions = {s: ls for s, ls in short_names.items() if len(ls) > 1}
    for label, item in by_label.items():
        # Canonical ID = full label, ALWAYS. A short name that is unique today can
        # collide tomorrow; an ID that changes when a neighbor appears would sever
        # ledger history, watchdog matching, and digests. Short names are display only.
        item["job"] = label
        item["display_name"] = job_name_from_label(label)
    return {
        "version": 2,
        "entries": sorted(by_label.values(), key=lambda i: str(i["label"])),
        "collisions": collisions,
        "errors": errors,
    }


def diff_drift(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, list[str]]:
    """Report source drift between generated files: added / removed / changed plists."""
    old_map = {e["label"]: e for e in (old or {}).get("entries", [])}
    new_map = {e["label"]: e for e in new.get("entries", [])}
    return {
        "added": sorted(set(new_map) - set(old_map)),
        "removed": sorted(set(old_map) - set(new_map)),
        "changed": sorted(
            label
            for label in set(old_map) & set(new_map)
            if old_map[label].get("source_hash") != new_map[label].get("source_hash")
        ),
    }


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """None if absent; raises ValueError on corrupt user files (fail loudly)."""
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML — {exc}") from exc
    if data is not None and not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    return data or {}


def init_workspace(config_dir: Path, launchagents_dir: Path) -> dict[str, Any]:
    """Discover + regenerate candidates. Holds a single-instance lock; atomic writes;
    never touches the user file (creates the commented template only if absent)."""
    config_dir.mkdir(parents=True, exist_ok=True)
    config_dir.chmod(0o700)
    lock_fd = os.open(config_dir / ".init.lock", os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("another qd init is running (init lock held)") from None

        summary: dict[str, Any] = {"created": [], "regenerated": []}
        config_yaml = config_dir / "config.yaml"
        if not config_yaml.exists():
            atomic_write(config_yaml, DEFAULT_CONFIG.encode(), mode=0o600)
            summary["created"].append(str(config_yaml))
        user_yaml = config_dir / USER_NAME
        if not user_yaml.exists():
            atomic_write(user_yaml, USER_TEMPLATE.encode(), mode=0o600)
            summary["created"].append(str(user_yaml))

        entries = scan(launchagents_dir) if launchagents_dir.exists() else []
        generated = build_generated(entries)
        gen_path = config_dir / GENERATED_NAME
        try:
            old = _load_yaml(gen_path)
        except ValueError:
            old = None  # machine-owned file corrupt → rebuild, report
            summary["generated_was_corrupt"] = True
        generated["drift"] = diff_drift(old, generated)
        atomic_write(
            gen_path,
            (
                "# MACHINE-OWNED — rebuilt by `qd init`; put your edits in schedules.yaml\n"
                + yaml.safe_dump(generated, allow_unicode=True, sort_keys=False)
            ).encode(),
            mode=0o600,
        )
        summary["regenerated"].append(str(gen_path))

        counts = {"interval": 0, "calendar": 0, "service": 0}
        for e in generated["entries"]:
            counts[e["class"]] += 1
        summary["counts"] = counts
        summary["collisions"] = generated["collisions"]
        summary["drift"] = generated["drift"]
        summary["errors"] = generated["errors"]
        return summary
    finally:
        os.close(lock_fd)


def load_effective_schedules(config_dir: Path) -> dict[str, Any]:
    """Deterministic merge: generated facts × user enrollment/overrides.

    Returns {"schedules": [watchdog entries for ENROLLED interval+calendar jobs],
             "meta": {enrolled, candidates, services, unknown_enroll_patterns}}.
    User file errors raise (fail loudly); a missing generated file yields no coverage.
    """
    generated = _load_yaml(config_dir / GENERATED_NAME) or {"entries": []}
    raw_user = _load_yaml(config_dir / USER_NAME) or {}
    if "retired" in raw_user:
        raise ValueError(
            f"{config_dir / USER_NAME}: `retired:` was removed; use "
            "`qd retire JOB --reason ...` so retirement remains auditable"
        )
    try:
        user = UserSchedulesConfig.model_validate(raw_user)
    except ValidationError as exc:
        raise ValueError(f"{config_dir / USER_NAME}: schema violation — {exc}") from exc
    patterns = user.enroll
    overrides = user.overrides

    schedules: list[dict[str, Any]] = []
    meta: dict[str, Any] = {
        "enrolled": 0,
        "candidates": 0,
        "services": 0,
        "unknown_enroll_patterns": [],
        "disabled_jobs": [],
        "unsupported_jobs": [],
    }
    matched_patterns: set[str] = set()
    for entry in generated.get("entries", []):
        label = entry["label"]
        enrolled = False
        for pat in patterns:
            if fnmatch.fnmatch(label, pat):
                enrolled = True
                matched_patterns.add(pat)
        if entry["class"] == "service":
            meta["services"] += 1
            continue  # services are never auto-monitorable
        if not enrolled:
            meta["candidates"] += 1
            continue
        override = overrides.get(label)
        sched: dict[str, Any] = {
            "job": entry.get("job", label),  # canonical = full label
            "label": label,
            "display_name": entry.get("display_name", job_name_from_label(label)),
        }
        if entry["class"] == "interval":
            sched["expected_interval_seconds"] = entry["expected_interval_seconds"]
            sched["grace_seconds"] = entry.get("grace_seconds", 300)
        # calendar: no interval key → watchdog reports it as unsupported (fail-closed)
        if override and override.grace_seconds is not None:
            sched["grace_seconds"] = override.grace_seconds
        if override and override.enabled is False:
            sched["enabled"] = False
        schedules.append(sched)
        meta["enrolled"] += 1
        state = classify_schedule(sched)
        if state == "disabled":
            meta["disabled"] = meta.get("disabled", 0) + 1
            meta["disabled_jobs"].append(sched["job"])
        elif state == "unsupported":
            meta["unsupported_jobs"].append(sched["job"])
    meta["unknown_enroll_patterns"] = [p for p in patterns if p not in matched_patterns]
    return {"schedules": schedules, "meta": meta}
