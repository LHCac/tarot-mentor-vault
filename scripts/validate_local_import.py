#!/usr/bin/env python3
"""Read-only integrity checks for the current local tarot import.

The validator intentionally uses only the Python standard library.  It checks
the generated Markdown against the canonical card registry used by
``import_pages_docx.py`` and prints a machine-readable JSON report to stdout.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

from card_sections import (
    CANONICAL_SECTION_KEYS,
    SECTION_LABELS,
    find_card_sections,
)
from import_pages_docx import CUPS, MAJORS, WANDS, CardSpec


CARD_FRONTMATTER_KEYS = {
    "schema_version",
    "id",
    "deck_system",
    "arcana",
    "suit",
    "number",
    "rank",
    "name_zh",
    "name_en",
    "aliases",
    "keywords_upright",
    "keywords_reversed",
    "correspondences",
    "summary",
    "source_ids",
    "review_status",
    "last_reviewed",
}
COMBINATION_FRONTMATTER_KEYS = {
    "schema_version",
    "id",
    "deck_system",
    "source_card_id",
    "directional",
    "source_ids",
    "review_status",
    "last_reviewed",
}
FOUNDATION_FRONTMATTER_KEYS = {
    "schema_version",
    "source_ids",
    "review_status",
    "last_reviewed",
}
CORRESPONDENCE_KEYS = {"element", "planet", "zodiac", "timing"}
IMPORTED_FOUNDATION_FILES = 2
IMPORTED_CARD_EXTERNAL_LINKS = 60
IMPORTED_COMBINATION_EXTERNAL_LINKS = 462
IMPORTED_EXTERNAL_LINKS_TOTAL = 522
SOURCE_HYPERLINKS_DETECTED = 525
EXCLUDED_SOURCE_HYPERLINKS = 3
CURATED_CARD_EXTERNAL_LINKS = 57
CURATED_CARD_EXTERNAL_LINK_DELTA = -3
CURATED_FOUNDATION_REFERENCE_FILES = 1
CURATED_FOUNDATION_FILES_TOTAL = 3
SEMANTIC_HEADINGS = {
    "upright": re.compile(r"^#{2,6}\s+.*正位", re.MULTILINE),
    "reversed": re.compile(r"^#{2,6}\s+.*逆位", re.MULTILINE),
    "spread": re.compile(r"^#{2,6}\s+.*牌陣", re.MULTILINE),
    "yes_no": re.compile(
        r"^#{2,6}\s+.*(?:是或否|是否|是非|Yes\s*(?:or|/|／)\s*No)",
        re.MULTILINE | re.IGNORECASE,
    ),
    "faq": re.compile(r"^#{2,6}\s+.*(?:FAQ|Q&A|常見問題)", re.MULTILINE | re.IGNORECASE),
}
H1_RE = re.compile(r"^# (?!#)(.+)$", re.MULTILINE)
MARKDOWN_EXTERNAL_LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)", re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RWS_MAJOR_NUMBERS = {
    "The Fool": 0,
    "Strength": 8,
    "Justice": 11,
    "Judgement": 20,
    "The World": 21,
}
BODY_CORRESPONDENCE_LABELS = {
    "元素": "element",
    "行星": "planet",
    "星座": "zodiac",
    "星座連結": "zodiac",
    "關鍵日期": "timing",
    "關鍵時間象徵": "timing",
    "關鍵季節象徵": "timing",
    "時間": "timing",
    "時機": "timing",
}


class Validation:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.errors: list[str] = []
        self.counts: dict[str, int] = {
            "cards_total": 0,
            "cards_major_arcana": 0,
            "cards_wands": 0,
            "cards_cups": 0,
            "combination_files": 0,
            "directional_combination_rows": 0,
            "undirected_major_pairs": 0,
            "card_body_external_links": 0,
            "combination_external_links": 0,
            "foundation_files": 0,
        }

    def error(self, location: str | Path, message: str) -> None:
        if isinstance(location, Path):
            try:
                label = str(location.relative_to(self.root))
            except ValueError:
                label = str(location)
        else:
            label = location
        self.errors.append(f"{label}: {message}")

    def expect(self, condition: bool, location: str | Path, message: str) -> None:
        if not condition:
            self.error(location, message)


def values_match(actual: Any, expected: Any) -> bool:
    """Compare JSON/YAML values without treating booleans as integers."""
    if isinstance(expected, bool):
        return isinstance(actual, bool) and actual is expected
    if isinstance(expected, int):
        return type(actual) is int and actual == expected
    return actual == expected


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith(('"', "[", "{")):
        return json.loads(value)
    return value


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("missing closing frontmatter delimiter") from exc

    metadata: dict[str, Any] = {}
    active_mapping: str | None = None
    for number, line in enumerate(lines[1:end], start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  "):
            if active_mapping is None:
                raise ValueError(f"line {number}: nested value without a parent")
            key, separator, raw = line.strip().partition(":")
            if not separator or not key:
                raise ValueError(f"line {number}: malformed nested field")
            mapping = metadata[active_mapping]
            if key in mapping:
                raise ValueError(f"line {number}: duplicate field {active_mapping}.{key}")
            mapping[key] = parse_scalar(raw)
            continue
        key, separator, raw = line.partition(":")
        if not separator or not key:
            raise ValueError(f"line {number}: malformed field")
        if key in metadata:
            raise ValueError(f"line {number}: duplicate field {key}")
        if raw.strip():
            metadata[key] = parse_scalar(raw)
            active_mapping = None
        else:
            metadata[key] = {}
            active_mapping = key
    body = "\n".join(lines[end + 1 :]).lstrip("\n")
    return metadata, body


def read_markdown(validation: Validation, path: Path) -> tuple[dict[str, Any], str] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        validation.error(path, f"cannot read UTF-8 Markdown: {exc}")
        return None
    try:
        return split_frontmatter(text)
    except (ValueError, json.JSONDecodeError) as exc:
        validation.error(path, f"invalid frontmatter: {exc}")
        return None


def check_key_set(
    validation: Validation,
    path: Path,
    metadata: dict[str, Any],
    expected: set[str],
) -> None:
    missing = sorted(expected - set(metadata))
    extra = sorted(set(metadata) - expected)
    if missing:
        validation.error(path, f"missing frontmatter keys: {', '.join(missing)}")
    if extra:
        validation.error(path, f"unexpected frontmatter keys: {', '.join(extra)}")


def check_review_fields(validation: Validation, path: Path, metadata: dict[str, Any]) -> None:
    validation.expect(metadata.get("review_status") in {"draft", "reviewed"}, path, "review_status must be draft or reviewed")
    reviewed = metadata.get("last_reviewed")
    if reviewed is None:
        return
    valid = isinstance(reviewed, str) and DATE_RE.fullmatch(reviewed) is not None
    if valid:
        try:
            dt.date.fromisoformat(reviewed)
        except ValueError:
            valid = False
    validation.expect(valid, path, "last_reviewed must be null or a valid YYYY-MM-DD date")


def check_string_list(
    validation: Validation,
    path: Path,
    field: str,
    value: Any,
    *,
    nonempty: bool,
) -> None:
    valid = isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
    if nonempty:
        valid = valid and bool(value)
    if valid:
        valid = len(value) == len(set(value))
    suffix = "a non-empty " if nonempty else "a "
    validation.expect(valid, path, f"{field} must be {suffix}list of unique non-empty strings")


def check_single_h1(validation: Validation, path: Path, body: str, expected: str | None = None) -> None:
    headings = H1_RE.findall(body)
    validation.expect(len(headings) == 1, path, f"expected exactly one H1, found {len(headings)}")
    if expected is not None and len(headings) == 1:
        validation.expect(headings[0].strip() == expected, path, f"H1 must be {expected!r}")


def actual_content_paths(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {
        str(path)
        for path in directory.rglob("*.md")
        if path.name.lower() != "readme.md"
    }


def body_correspondences(body: str) -> dict[str, str]:
    """Read the first visible correspondence value for each field.

    This mirrors the labels accepted by the importer and catches a regression
    where Pages line breaks were preserved in the card body but skipped while
    creating frontmatter.
    """
    result: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        match = re.match(r"^([^：:]+)\s*[：:]\s*(.+)$", line)
        if not match:
            continue
        field = BODY_CORRESPONDENCE_LABELS.get(match.group(1).strip())
        if field is None or field in result:
            continue
        value = MARKDOWN_LINK_RE.sub(r"\1", match.group(2)).strip()
        if value:
            result[field] = value
    return result


def validate_card(validation: Validation, spec: CardSpec) -> int:
    path = validation.root / spec.path
    parsed = read_markdown(validation, path)
    if parsed is None:
        return 0
    metadata, body = parsed
    check_key_set(validation, path, metadata, CARD_FRONTMATTER_KEYS)

    expected_fields = {
        "schema_version": 1,
        "id": spec.id,
        "deck_system": "rider-waite-smith",
        "arcana": spec.arcana,
        "suit": spec.suit,
        "number": spec.number,
        "rank": spec.rank,
        "name_zh": spec.name_zh,
        "name_en": spec.name_en,
        "aliases": list(spec.aliases),
        "source_ids": [spec.source_id],
    }
    for field, expected in expected_fields.items():
        validation.expect(values_match(metadata.get(field), expected), path, f"{field} must equal {expected!r}")

    for field in ("keywords_upright", "keywords_reversed"):
        check_string_list(validation, path, field, metadata.get(field), nonempty=True)
    check_string_list(validation, path, "aliases", metadata.get("aliases"), nonempty=False)

    correspondences = metadata.get("correspondences")
    valid_correspondences = isinstance(correspondences, dict) and set(correspondences) == CORRESPONDENCE_KEYS
    validation.expect(valid_correspondences, path, "correspondences must contain exactly element, planet, zodiac, and timing")
    if isinstance(correspondences, dict):
        for field in CORRESPONDENCE_KEYS:
            value = correspondences.get(field)
            validation.expect(value is None or (isinstance(value, str) and value.strip()), path, f"correspondences.{field} must be null or a non-empty string")
        for field, visible_value in body_correspondences(body).items():
            validation.expect(
                correspondences.get(field) == visible_value,
                path,
                f"correspondences.{field} must match the first body value {visible_value!r}",
            )

    summary = metadata.get("summary")
    validation.expect(isinstance(summary, str) and bool(summary.strip()), path, "summary must be a non-empty string")
    check_review_fields(validation, path, metadata)
    check_single_h1(validation, path, body, f"{spec.name_zh}｜{spec.name_en}")
    for label, pattern in SEMANTIC_HEADINGS.items():
        validation.expect(pattern.search(body) is not None, path, f"body is missing a {label} semantic heading")

    sections = find_card_sections(body)
    counts = {
        key: sum(section.key == key for section in sections)
        for key in CANONICAL_SECTION_KEYS
    }
    for key in CANONICAL_SECTION_KEYS:
        validation.expect(
            counts[key] == 1,
            path,
            f"expected exactly one {SECTION_LABELS[key]} section, found {counts[key]}",
        )
    if all(counts[key] == 1 for key in CANONICAL_SECTION_KEYS):
        actual_order = tuple(section.key for section in sections)
        validation.expect(
            actual_order == CANONICAL_SECTION_KEYS,
            path,
            "canonical sections must appear in order: "
            + ", ".join(SECTION_LABELS[key] for key in CANONICAL_SECTION_KEYS),
        )
        for section in sections:
            validation.expect(
                bool(section.content),
                path,
                f"{SECTION_LABELS[section.key]} section must not be empty",
            )
    return len(MARKDOWN_EXTERNAL_LINK_RE.findall(body))


def parse_table_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", stripped[1:-1])]


def combination_relative_path(spec: CardSpec) -> str:
    return f"knowledge/combinations/major-arcana/{spec.number:02d}-{spec.slug}.md"


def validate_combination_file(
    validation: Validation,
    source: CardSpec,
    major_by_id: dict[str, CardSpec],
) -> tuple[set[tuple[str, str]], int]:
    path = validation.root / combination_relative_path(source)
    parsed = read_markdown(validation, path)
    if parsed is None:
        return set(), 0
    metadata, body = parsed
    check_key_set(validation, path, metadata, COMBINATION_FRONTMATTER_KEYS)
    expected_fields = {
        "schema_version": 1,
        "id": f"combination-{source.id}",
        "deck_system": "rider-waite-smith",
        "source_card_id": source.id,
        "directional": True,
        "source_ids": [source.source_id],
    }
    for field, expected in expected_fields.items():
        validation.expect(values_match(metadata.get(field), expected), path, f"{field} must equal {expected!r}")
    check_review_fields(validation, path, metadata)
    check_single_h1(validation, path, body, f"{source.name_zh}為主牌的組合牌義")

    lines = body.splitlines()
    expected_header = ["搭配牌 ID", "搭配牌", "組合意義", "原始參考"]
    header_index: int | None = None
    for index, line in enumerate(lines):
        if parse_table_row(line) == expected_header:
            header_index = index
            break
    if header_index is None:
        validation.error(path, "missing expected four-column combination table")
        return set(), len(MARKDOWN_EXTERNAL_LINK_RE.findall(body))
    if header_index + 1 >= len(lines):
        validation.error(path, "combination table is missing its separator row")
        return set(), len(MARKDOWN_EXTERNAL_LINK_RE.findall(body))
    separator = parse_table_row(lines[header_index + 1])
    valid_separator = separator is not None and len(separator) == 4 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)
    validation.expect(valid_separator, path, "combination table has an invalid separator row")

    data_rows: list[list[str]] = []
    for line in lines[header_index + 2 :]:
        row = parse_table_row(line)
        if row is None:
            if data_rows:
                break
            continue
        data_rows.append(row)
    validation.expect(len(data_rows) == 21, path, f"expected 21 combination rows, found {len(data_rows)}")

    edges: set[tuple[str, str]] = set()
    seen_targets: set[str] = set()
    for row_number, row in enumerate(data_rows, start=1):
        if len(row) != 4:
            validation.error(path, f"combination row {row_number} has {len(row)} columns, expected 4")
            continue
        target_id, label, meaning, source_link = row
        target = major_by_id.get(target_id)
        if target is None:
            validation.error(path, f"combination row {row_number} has unknown target {target_id!r}")
            continue
        if target_id == source.id:
            validation.error(path, f"combination row {row_number} is a self edge")
        if target_id in seen_targets:
            validation.error(path, f"combination row {row_number} duplicates target {target_id}")
        seen_targets.add(target_id)
        validation.expect(label == f"{target.number} {target.name_zh}｜{target.name_en}", path, f"combination row {row_number} has the wrong target label")
        validation.expect(bool(meaning.strip()), path, f"combination row {row_number} has an empty meaning")
        links = MARKDOWN_EXTERNAL_LINK_RE.findall(source_link)
        validation.expect(len(links) == 1, path, f"combination row {row_number} must contain exactly one external source link")
        edges.add((source.id, target_id))

    expected_targets = set(major_by_id) - {source.id}
    missing = sorted(expected_targets - seen_targets)
    extra = sorted(seen_targets - expected_targets)
    if missing or extra:
        validation.error(path, f"target set mismatch; missing={missing}, extra={extra}")
    external_links = len(MARKDOWN_EXTERNAL_LINK_RE.findall(body))
    validation.expect(external_links == 21, path, f"expected 21 external links, found {external_links}")
    return edges, external_links


def validate_foundations(validation: Validation) -> None:
    directory = validation.root / "knowledge/foundations"
    expected_sources = {
        directory / "tarot-structure-source.md": "src-major-00-05",
        directory / "minor-arcana-wands-source.md": "src-wands-01-14",
    }
    expected_references = {directory / "correspondence-policy.md"}
    actual = {Path(path) for path in actual_content_paths(directory)}
    actual_sources = {path for path in actual if path.name.endswith("-source.md")}
    actual_references = actual - actual_sources
    validation.counts["foundation_files"] = len(actual_sources)
    validation.counts["foundation_reference_files"] = len(actual_references)
    validation.counts["foundation_files_total"] = len(actual)
    validation.expect(
        len(actual_references) == CURATED_FOUNDATION_REFERENCE_FILES,
        "knowledge/foundations",
        f"expected {CURATED_FOUNDATION_REFERENCE_FILES} authored reference file, found {len(actual_references)}",
    )
    validation.expect(
        len(actual) == CURATED_FOUNDATION_FILES_TOTAL,
        "knowledge/foundations",
        f"expected {CURATED_FOUNDATION_FILES_TOTAL} total foundation files, found {len(actual)}",
    )

    expected_source_paths = set(expected_sources)
    missing = sorted(str(path.relative_to(validation.root)) for path in expected_source_paths - actual_sources)
    extra = sorted(str(path.relative_to(validation.root)) for path in actual_sources - expected_source_paths)
    if missing:
        validation.error("knowledge/foundations", f"missing imported foundation files: {', '.join(missing)}")
    if extra:
        validation.error("knowledge/foundations", f"unexpected imported foundation files: {', '.join(extra)}")
    validation.expect(
        len(actual_sources) == IMPORTED_FOUNDATION_FILES,
        "knowledge/foundations",
        f"expected {IMPORTED_FOUNDATION_FILES} imported foundation files, found {len(actual_sources)}",
    )

    missing_references = sorted(
        str(path.relative_to(validation.root))
        for path in expected_references - actual_references
    )
    extra_references = sorted(
        str(path.relative_to(validation.root))
        for path in actual_references - expected_references
    )
    if missing_references:
        validation.error("knowledge/foundations", f"missing authored reference files: {', '.join(missing_references)}")
    if extra_references:
        validation.error("knowledge/foundations", f"unexpected authored reference files: {', '.join(extra_references)}")

    for path, source_id in expected_sources.items():
        if not path.is_file():
            continue
        parsed = read_markdown(validation, path)
        if parsed is None:
            continue
        metadata, body = parsed
        check_key_set(validation, path, metadata, FOUNDATION_FRONTMATTER_KEYS)
        validation.expect(metadata.get("schema_version") == 1, path, "schema_version must equal 1")
        validation.expect(metadata.get("source_ids") == [source_id], path, f"source_ids must equal {[source_id]!r}")
        check_review_fields(validation, path, metadata)
        check_single_h1(validation, path, body)

    for path in expected_references:
        try:
            body = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            validation.error(path, f"cannot read authored reference: {exc}")
            continue
        check_single_h1(validation, path, body)


def expect_report_value(
    validation: Validation,
    report: dict[str, Any],
    path: Sequence[str],
    expected: Any,
) -> None:
    value: Any = report
    for component in path:
        if not isinstance(value, dict) or component not in value:
            validation.error("qa/import-report.json", f"missing key {'.'.join(path)}")
            return
        value = value[component]
    validation.expect(values_match(value, expected), "qa/import-report.json", f"{'.'.join(path)} must equal {expected!r}, found {value!r}")


def validate_import_report(validation: Validation) -> None:
    path = validation.root / "qa/import-report.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        validation.error(path, f"cannot read valid JSON: {exc}")
        return
    if not isinstance(report, dict):
        validation.error(path, "top-level JSON value must be an object")
        return
    checks = {
        ("schema_version",): 1,
        ("publish_allowed",): False,
        ("rights_status",): "unknown",
        ("cards", "total"): validation.counts["cards_total"],
        ("cards", "major_arcana"): validation.counts["cards_major_arcana"],
        ("cards", "wands"): validation.counts["cards_wands"],
        ("cards", "cups"): validation.counts["cards_cups"],
        ("combination_files",): validation.counts["combination_files"],
        ("directional_combination_rows",): validation.counts["directional_combination_rows"],
        ("undirected_major_pairs",): validation.counts["undirected_major_pairs"],
        # import-report.json records the immutable raw-import baseline. Reviewed
        # overrides may later remove a bad source link or add an authored
        # foundation without rewriting that provenance report.
        ("foundation_files",): IMPORTED_FOUNDATION_FILES,
        ("source_hyperlinks_detected",): SOURCE_HYPERLINKS_DETECTED,
        ("hyperlinks_excluded",): EXCLUDED_SOURCE_HYPERLINKS,
        ("hyperlinks_preserved",): IMPORTED_EXTERNAL_LINKS_TOTAL,
    }
    for key_path, expected in checks.items():
        expect_report_value(validation, report, key_path, expected)


def compare_path_sets(
    validation: Validation,
    location: str,
    actual: Iterable[str],
    expected: Iterable[str],
) -> None:
    actual_set = set(actual)
    expected_set = set(expected)
    missing = sorted(expected_set - actual_set)
    extra = sorted(actual_set - expected_set)
    if missing:
        validation.error(location, f"missing files: {', '.join(missing)}")
    if extra:
        validation.error(location, f"unexpected files: {', '.join(extra)}")


def validate_repository(root: Path) -> Validation:
    validation = Validation(root)
    cards = tuple(MAJORS) + tuple(WANDS) + tuple(CUPS)

    major_numbers = {card.number for card in MAJORS}
    wand_numbers = {card.number for card in WANDS}
    cup_numbers = {card.number for card in CUPS}
    validation.expect(major_numbers == set(range(22)), "card registry", "Major Arcana numbers must be exactly 0 through 21")
    validation.expect(22 not in major_numbers, "card registry", "RWS Major Arcana must not contain card number 22")
    validation.expect(wand_numbers == set(range(1, 15)), "card registry", "Wands numbers must be exactly 1 through 14")
    validation.expect(cup_numbers == set(range(1, 15)), "card registry", "Cups numbers must be exactly 1 through 14")
    major_by_english_name = {card.name_en: card.number for card in MAJORS}
    for name, number in RWS_MAJOR_NUMBERS.items():
        validation.expect(major_by_english_name.get(name) == number, "card registry", f"RWS numbering requires {name} at {number}")

    card_directory = root / "knowledge/cards"
    actual_card_paths = actual_content_paths(card_directory)
    expected_card_paths = {str(root / card.path) for card in cards}
    compare_path_sets(validation, "knowledge/cards", actual_card_paths, expected_card_paths)
    validation.counts["cards_total"] = len(actual_card_paths)
    validation.counts["cards_major_arcana"] = len(
        actual_content_paths(root / "knowledge/cards/major-arcana")
    )
    validation.counts["cards_wands"] = len(
        actual_content_paths(root / "knowledge/cards/minor-arcana/wands")
    )
    validation.counts["cards_cups"] = len(
        actual_content_paths(root / "knowledge/cards/minor-arcana/cups")
    )
    validation.expect(validation.counts["cards_total"] == 50, "knowledge/cards", f"expected 50 card files, found {validation.counts['cards_total']}")
    validation.expect(validation.counts["cards_major_arcana"] == 22, "knowledge/cards/major-arcana", f"expected 22 Major Arcana files, found {validation.counts['cards_major_arcana']}")
    validation.expect(validation.counts["cards_wands"] == 14, "knowledge/cards/minor-arcana/wands", f"expected 14 Wands files, found {validation.counts['cards_wands']}")
    validation.expect(validation.counts["cards_cups"] == 14, "knowledge/cards/minor-arcana/cups", f"expected 14 Cups files, found {validation.counts['cards_cups']}")

    card_links = 0
    for card in cards:
        if (root / card.path).is_file():
            card_links += validate_card(validation, card)
    validation.counts["card_body_external_links"] = card_links
    validation.counts["card_body_external_links_imported_baseline"] = (
        IMPORTED_CARD_EXTERNAL_LINKS
    )
    validation.counts["card_body_external_link_delta"] = (
        card_links - IMPORTED_CARD_EXTERNAL_LINKS
    )
    validation.expect(
        card_links == CURATED_CARD_EXTERNAL_LINKS,
        "knowledge/cards",
        f"expected {CURATED_CARD_EXTERNAL_LINKS} curated card-body external links, found {card_links}",
    )
    validation.expect(
        validation.counts["card_body_external_link_delta"]
        == CURATED_CARD_EXTERNAL_LINK_DELTA,
        "knowledge/cards",
        f"expected curated link delta {CURATED_CARD_EXTERNAL_LINK_DELTA}, found {validation.counts['card_body_external_link_delta']}",
    )

    combination_directory = root / "knowledge/combinations/major-arcana"
    actual_combination_paths = actual_content_paths(combination_directory)
    expected_combination_paths = {str(root / combination_relative_path(card)) for card in MAJORS}
    compare_path_sets(validation, "knowledge/combinations/major-arcana", actual_combination_paths, expected_combination_paths)
    validation.counts["combination_files"] = len(actual_combination_paths)
    validation.expect(validation.counts["combination_files"] == 22, "knowledge/combinations/major-arcana", f"expected 22 combination files, found {validation.counts['combination_files']}")

    major_by_id = {card.id: card for card in MAJORS}
    directed_edges: set[tuple[str, str]] = set()
    combination_links = 0
    for source in MAJORS:
        if (root / combination_relative_path(source)).is_file():
            edges, links = validate_combination_file(validation, source, major_by_id)
            overlap = directed_edges & edges
            if overlap:
                validation.error("knowledge/combinations/major-arcana", f"duplicate directed edges: {sorted(overlap)}")
            directed_edges.update(edges)
            combination_links += links
    undirected_pairs = {tuple(sorted(edge)) for edge in directed_edges}
    validation.counts["directional_combination_rows"] = len(directed_edges)
    validation.counts["undirected_major_pairs"] = len(undirected_pairs)
    validation.counts["combination_external_links"] = combination_links
    validation.expect(len(directed_edges) == 462, "knowledge/combinations/major-arcana", f"expected 462 directed edges, found {len(directed_edges)}")
    validation.expect(len(undirected_pairs) == 231, "knowledge/combinations/major-arcana", f"expected 231 undirected pairs, found {len(undirected_pairs)}")
    validation.expect(
        combination_links == IMPORTED_COMBINATION_EXTERNAL_LINKS,
        "knowledge/combinations/major-arcana",
        f"expected {IMPORTED_COMBINATION_EXTERNAL_LINKS} external links, found {combination_links}",
    )

    validate_foundations(validation)
    validate_import_report(validation)
    return validation


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = args.root.resolve()
    try:
        validation = validate_repository(root)
        payload = {
            "schema_version": 1,
            "validator": "validate_local_import.py",
            "root": str(root),
            "ok": not validation.errors,
            "counts": validation.counts,
            "error_count": len(validation.errors),
            "errors": validation.errors,
        }
        status = 0 if payload["ok"] else 1
    except Exception as exc:  # Always preserve the JSON-output contract.
        payload = {
            "schema_version": 1,
            "validator": "validate_local_import.py",
            "root": str(root),
            "ok": False,
            "counts": {},
            "error_count": 1,
            "errors": [f"validator failure: {type(exc).__name__}: {exc}"],
        }
        status = 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
