#!/usr/bin/env python3
"""Build local JSON indexes from deck.yaml and validated card Markdown.

The generated index contains source-derived summaries and keywords.  While the
source catalog says publish=false, this script refuses to write into a Git
worktree so the index cannot be added to the public repository accidentally.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path
from typing import Sequence


def parse_scalar(value: str) -> object:
    value = value.strip()
    if value == "null":
        return None
    if value in {"true", "false"}:
        return value == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith(('"', "[", "{")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [part.strip().strip('"\'') for part in inner.split(",") if part.strip()]
    return value.strip('"\'')


def split_inline_fields(text: str) -> list[str]:
    fields: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote:
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char in "[{(":
            depth += 1
        elif char in "]})":
            depth -= 1
        elif char == "," and depth == 0:
            fields.append(text[start:index].strip())
            start = index + 1
    fields.append(text[start:].strip())
    return fields


def parse_deck(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- {") or not stripped.endswith("}"):
            continue
        inner = stripped[3:-1]
        record: dict[str, object] = {}
        for field in split_inline_fields(inner):
            key, separator, value = field.partition(":")
            if not separator:
                raise ValueError(f"Malformed deck field: {field!r}")
            record[key.strip()] = parse_scalar(value)
        records.append(record)
    if len(records) != 78:
        raise ValueError(f"Expected 78 deck records, got {len(records)}")
    return records


def parse_frontmatter(path: Path) -> dict[str, object]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{path}: missing YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError(f"{path}: unclosed YAML frontmatter") from error
    result: dict[str, object] = {}
    parent: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  "):
            if parent is None or not isinstance(result.get(parent), dict):
                raise ValueError(f"{path}: unexpected nested frontmatter line {line!r}")
            key, separator, value = line.strip().partition(":")
            if not separator:
                raise ValueError(f"{path}: malformed frontmatter line {line!r}")
            nested = result[parent]
            assert isinstance(nested, dict)
            nested[key] = parse_scalar(value)
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"{path}: malformed frontmatter line {line!r}")
        if value.strip():
            result[key] = parse_scalar(value)
            parent = None
        else:
            result[key] = {}
            parent = key
    return result


def update_deck_statuses(path: Path, root: Path) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = 0
    output: list[str] = []
    for line in lines:
        path_match = re.search(r"\bpath:\s*([^,}]+)", line)
        status_match = re.search(r"\bstatus:\s*([^,}]+)", line)
        if path_match and status_match:
            card_path = root / path_match.group(1).strip().strip('"\'')
            if card_path.is_file():
                metadata = parse_frontmatter(card_path)
                desired = str(metadata.get("review_status", "draft"))
                current = status_match.group(1).strip()
                if current != desired:
                    line = line[: status_match.start(1)] + desired + line[status_match.end(1) :]
                    changed += 1
        output.append(line)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    return changed


def build(root: Path, update_status: bool) -> tuple[list[dict[str, object]], dict[str, object], int]:
    deck_path = root / "catalog/deck.yaml"
    status_changes = update_deck_statuses(deck_path, root) if update_status else 0
    records = parse_deck(deck_path)
    index: list[dict[str, object]] = []
    counts: collections.Counter[str] = collections.Counter()
    available_by_arcana: collections.Counter[str] = collections.Counter()
    available_by_suit: collections.Counter[str] = collections.Counter()
    missing_ids: list[str] = []
    for record in records:
        relative_path = str(record["path"])
        card_path = root / relative_path
        entry = dict(record)
        if card_path.is_file():
            metadata = parse_frontmatter(card_path)
            for key in (
                "aliases",
                "keywords_upright",
                "keywords_reversed",
                "correspondences",
                "summary",
                "source_ids",
                "review_status",
                "last_reviewed",
            ):
                entry[key] = metadata.get(key)
            entry["status"] = metadata.get("review_status", "draft")
            entry["available_locally"] = True
            available_by_arcana[str(record["arcana"])] += 1
            if record.get("suit"):
                available_by_suit[str(record["suit"])] += 1
        else:
            entry["available_locally"] = False
            missing_ids.append(str(record["id"]))
        counts[str(entry["status"])] += 1
        index.append(entry)
    coverage: dict[str, object] = {
        "schema_version": 1,
        "deck_system": "rider-waite-smith",
        "publish_allowed": False,
        "rights_status": "unknown",
        "total_cards": len(records),
        "available_locally": sum(1 for entry in index if entry["available_locally"]),
        "missing_locally": len(missing_ids),
        "available_by_arcana": dict(sorted(available_by_arcana.items())),
        "available_by_suit": {
            suit: available_by_suit.get(suit, 0)
            for suit in ("wands", "cups", "swords", "pentacles")
        },
        "status_counts": dict(sorted(counts.items())),
        "missing_ids": missing_ids,
    }
    return index, coverage, status_changes


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--write", action="store_true", help="Write local JSON indexes")
    parser.add_argument(
        "--update-deck-status",
        action="store_true",
        help="Change import-planned entries with local files to their frontmatter review_status",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = args.root.resolve()
    try:
        if args.update_deck_status and not args.write:
            raise ValueError("--update-deck-status requires --write")
        if args.write and (root / ".git").exists():
            raise ValueError(
                "Refusing to write a source-derived local index inside a Git worktree while publish=false"
            )
        index, coverage, status_changes = build(root, args.update_deck_status)
        if args.write:
            (root / "catalog/card-index.json").write_text(
                json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (root / "catalog/coverage.json").write_text(
                json.dumps(coverage, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "write" if args.write else "check-only",
                    "index_entries": len(index),
                    "deck_status_changes": status_changes,
                    **coverage,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
