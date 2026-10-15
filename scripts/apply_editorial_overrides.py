#!/usr/bin/env python3
"""Safely apply reviewed literal text replacements inside a repository root.

The manifest may be either a JSON array of override objects or an object with
an ``overrides`` array.  Every override must contain ``path``, ``old``,
``new``, and ``expected_count``.  The command is a dry run unless ``--write``
is supplied, and stdout is always a JSON summary after argument parsing.
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


REQUIRED_FIELDS = {"path", "old", "new", "expected_count"}


@dataclass(frozen=True)
class Override:
    """One validated replacement instruction."""

    index: int
    path: Path
    relative_path: str
    old: str
    new: str
    expected_count: int


@dataclass(frozen=True)
class Snapshot:
    """Original file state retained until every validation has passed."""

    data: bytes
    text: str
    mode: int


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate literal editorial replacements and optionally apply them "
            "with atomic per-file writes."
        )
    )
    parser.add_argument("manifest", type=Path, help="JSON override manifest")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="allowed target root (default: repository root)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="apply replacements; without this flag the command is read-only",
    )
    return parser.parse_args(argv)


def add_error(
    errors: list[dict[str, Any]],
    code: str,
    message: str,
    *,
    index: int | None = None,
    path: str | None = None,
) -> None:
    error: dict[str, Any] = {"code": code, "message": message}
    if index is not None:
        error["index"] = index
    if path is not None:
        error["path"] = path
    errors.append(error)


def read_manifest(path: Path) -> tuple[list[Any], dict[str, Any] | None]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [], {"code": "manifest_read_error", "message": str(exc)}

    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return [], {"code": "manifest_parse_error", "message": str(exc)}

    if isinstance(document, list):
        return document, None
    if isinstance(document, dict) and isinstance(document.get("overrides"), list):
        return document["overrides"], None
    return [], {
        "code": "manifest_shape_error",
        "message": "manifest must be an array or an object containing an overrides array",
    }


def resolve_target(root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise ValueError("target path must be relative to root")
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("target path escapes root") from exc
    return resolved


def validate_items(
    raw_items: list[Any], root: Path, errors: list[dict[str, Any]]
) -> list[Override]:
    overrides: list[Override] = []
    seen_targets: dict[tuple[Path, str], int] = {}

    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            add_error(
                errors,
                "invalid_item",
                "override must be a JSON object",
                index=index,
            )
            continue

        missing = sorted(REQUIRED_FIELDS - set(item))
        if missing:
            add_error(
                errors,
                "missing_fields",
                f"missing required fields: {', '.join(missing)}",
                index=index,
            )
            continue

        raw_path = item["path"]
        old = item["old"]
        new = item["new"]
        expected_count = item["expected_count"]

        item_valid = True
        if not isinstance(raw_path, str) or not raw_path.strip():
            add_error(
                errors,
                "invalid_path",
                "path must be a non-empty string",
                index=index,
            )
            item_valid = False
        if not isinstance(old, str) or not old:
            add_error(
                errors,
                "invalid_old",
                "old must be a non-empty string",
                index=index,
            )
            item_valid = False
        if not isinstance(new, str):
            add_error(
                errors,
                "invalid_new",
                "new must be a string",
                index=index,
            )
            item_valid = False
        if (
            isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
            or expected_count < 1
        ):
            add_error(
                errors,
                "invalid_expected_count",
                "expected_count must be a positive integer",
                index=index,
            )
            item_valid = False
        if not item_valid:
            continue

        try:
            target = resolve_target(root, raw_path)
        except (OSError, ValueError) as exc:
            add_error(
                errors,
                "path_escape" if "escapes" in str(exc) else "invalid_path",
                str(exc),
                index=index,
                path=raw_path,
            )
            continue

        relative_path = target.relative_to(root).as_posix()
        duplicate_key = (target, old)
        if duplicate_key in seen_targets:
            first_index = seen_targets[duplicate_key]
            add_error(
                errors,
                "duplicate_target",
                f"same path and old text already used by override {first_index}",
                index=index,
                path=relative_path,
            )
            continue
        seen_targets[duplicate_key] = index

        overrides.append(
            Override(
                index=index,
                path=target,
                relative_path=relative_path,
                old=old,
                new=new,
                expected_count=expected_count,
            )
        )

    return overrides


def load_snapshots(
    overrides: list[Override], errors: list[dict[str, Any]]
) -> dict[Path, Snapshot]:
    snapshots: dict[Path, Snapshot] = {}
    path_labels = {override.path: override.relative_path for override in overrides}

    for path in sorted(path_labels, key=lambda item: path_labels[item]):
        label = path_labels[path]
        try:
            if not path.is_file():
                raise OSError("target is not an existing regular file")
            data = path.read_bytes()
            text = data.decode("utf-8")
            mode = stat.S_IMODE(path.stat().st_mode)
        except (OSError, UnicodeError) as exc:
            add_error(errors, "target_read_error", str(exc), path=label)
            continue
        snapshots[path] = Snapshot(data=data, text=text, mode=mode)

    return snapshots


def plan_replacements(
    overrides: list[Override],
    snapshots: dict[Path, Snapshot],
    errors: list[dict[str, Any]],
) -> tuple[dict[Path, bytes], list[dict[str, Any]]]:
    planned_text = {path: snapshot.text for path, snapshot in snapshots.items()}
    changes: list[dict[str, Any]] = []

    for override in overrides:
        snapshot = snapshots.get(override.path)
        if snapshot is None:
            continue

        found_count = snapshot.text.count(override.old)
        change = {
            "index": override.index,
            "path": override.relative_path,
            "expected_count": override.expected_count,
            "found_count": found_count,
        }
        changes.append(change)

        if found_count == 0:
            add_error(
                errors,
                "old_not_found",
                "old text was not found",
                index=override.index,
                path=override.relative_path,
            )
            continue
        if found_count != override.expected_count:
            add_error(
                errors,
                "count_mismatch",
                f"expected {override.expected_count} occurrence(s), found {found_count}",
                index=override.index,
                path=override.relative_path,
            )
            continue

        current = planned_text[override.path]
        current_count = current.count(override.old)
        if current_count != override.expected_count:
            add_error(
                errors,
                "interacting_overrides",
                (
                    "an earlier override changed this target; split the edits or "
                    "make their order independent"
                ),
                index=override.index,
                path=override.relative_path,
            )
            continue
        planned_text[override.path] = current.replace(
            override.old, override.new, override.expected_count
        )

    planned_bytes = {
        path: text.encode("utf-8") for path, text in planned_text.items()
    }
    return planned_bytes, changes


def stage_file(path: Path, data: bytes, mode: int, label: str) -> Path:
    descriptor, raw_temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.editorial-{label}-",
        suffix=".tmp",
    )
    temp_path = Path(raw_temp_path)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            os.fchmod(handle.fileno(), mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def atomic_commit(
    changed_paths: list[Path],
    planned: dict[Path, bytes],
    snapshots: dict[Path, Snapshot],
) -> tuple[list[Path], list[dict[str, Any]]]:
    staged_new: dict[Path, Path] = {}
    staged_backup: dict[Path, Path] = {}
    errors: list[dict[str, Any]] = []
    committed: list[Path] = []

    try:
        for path in changed_paths:
            snapshot = snapshots[path]
            staged_new[path] = stage_file(path, planned[path], snapshot.mode, "new")
            staged_backup[path] = stage_file(
                path, snapshot.data, snapshot.mode, "backup"
            )

        changed_during_run = [
            path for path in changed_paths if path.read_bytes() != snapshots[path].data
        ]
        if changed_during_run:
            for path in changed_during_run:
                add_error(
                    errors,
                    "target_changed",
                    "target changed after validation; nothing was applied",
                    path=str(path),
                )
            return [], errors

        for path in changed_paths:
            os.replace(staged_new[path], path)
            staged_new.pop(path, None)
            committed.append(path)
    except OSError as exc:
        rollback_errors: list[str] = []
        for path in reversed(committed):
            backup = staged_backup.get(path)
            if backup is None:
                continue
            try:
                os.replace(backup, path)
                staged_backup.pop(path, None)
            except OSError as rollback_exc:
                rollback_errors.append(f"{path}: {rollback_exc}")
        message = f"atomic write failed: {exc}"
        if rollback_errors:
            message += "; rollback failures: " + "; ".join(rollback_errors)
        add_error(errors, "write_error", message)
        return [], errors
    finally:
        for temp_path in [*staged_new.values(), *staged_backup.values()]:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    return committed, errors


def emit(summary: dict[str, Any]) -> None:
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    mode = "write" if args.write else "dry-run"
    manifest = args.manifest.resolve(strict=False)
    root = args.root.resolve(strict=False)
    summary: dict[str, Any] = {
        "ok": False,
        "mode": mode,
        "root": str(root),
        "manifest": str(manifest),
        "overrides_total": 0,
        "targets_total": 0,
        "matches_total": 0,
        "files_would_change": [],
        "files_modified": [],
        "changes": [],
        "errors": [],
    }

    if not root.is_dir():
        add_error(summary["errors"], "invalid_root", "root must be an existing directory")
        emit(summary)
        return 1

    raw_items, manifest_error = read_manifest(manifest)
    if manifest_error is not None:
        summary["errors"].append(manifest_error)
        emit(summary)
        return 1
    summary["overrides_total"] = len(raw_items)

    overrides = validate_items(raw_items, root, summary["errors"])
    snapshots = load_snapshots(overrides, summary["errors"])
    planned, changes = plan_replacements(overrides, snapshots, summary["errors"])
    summary["changes"] = changes
    summary["targets_total"] = len(snapshots)
    summary["matches_total"] = sum(
        change["found_count"]
        for change in changes
        if change["found_count"] == change["expected_count"]
    )

    changed_paths = sorted(
        (
            path
            for path, data in planned.items()
            if path in snapshots and data != snapshots[path].data
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    summary["files_would_change"] = [
        path.relative_to(root).as_posix() for path in changed_paths
    ]

    if summary["errors"]:
        emit(summary)
        return 1

    if args.write:
        committed, write_errors = atomic_commit(
            changed_paths, planned, snapshots
        )
        summary["errors"].extend(write_errors)
        summary["files_modified"] = [
            path.relative_to(root).as_posix() for path in committed
        ]
        if write_errors:
            emit(summary)
            return 1

    summary["ok"] = True
    emit(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
