#!/usr/bin/env python3
"""Locate and extract the five canonical long-form card sections.

Source exports do not always use an identical heading.  In particular, the
personality section may say either ``人物特質`` or
``作為一個人的特性`` and one existing source uses an H3 for that
section.  This module is shared by the local catalog builder and validator so
both tools use the same aliases and Markdown boundary rules.
"""

from __future__ import annotations

import dataclasses
import re


CANONICAL_SECTION_KEYS = (
    "key_features",
    "visual_description",
    "symbolism",
    "deeper_meaning",
    "person_traits",
)

SECTION_LABELS = {
    "key_features": "關鍵特徵",
    "visual_description": "牌面描述",
    "symbolism": "牌面象徵解析",
    "deeper_meaning": "深層含義",
    "person_traits": "人物特質｜作為一個人的特性",
}

_HEADING_RE = re.compile(
    r"^(?P<marks>#{2,6})[ \t]+(?P<title>.*?)[ \t]*#*[ \t]*$",
    re.MULTILINE,
)
_SECTION_PATTERNS = (
    ("key_features", re.compile(r"關鍵特徵")),
    ("visual_description", re.compile(r"牌面描述")),
    ("symbolism", re.compile(r"牌面象徵解析")),
    ("deeper_meaning", re.compile(r"深層含義")),
    ("person_traits", re.compile(r"(?:人物特質|作為一個人的特性)")),
)


@dataclasses.dataclass(frozen=True)
class MarkdownHeading:
    """A parsed Markdown heading and its source offsets."""

    title: str
    level: int
    start: int
    end: int


@dataclasses.dataclass(frozen=True)
class CardSection:
    """One canonical section occurrence in a card body."""

    key: str
    heading: str
    level: int
    start: int
    end: int
    content: str


def classify_section_heading(title: str) -> str | None:
    """Return the canonical key for a supported heading, if any."""

    normalized = re.sub(r"\s+", "", title)
    for key, pattern in _SECTION_PATTERNS:
        if pattern.search(normalized):
            return key
    return None


def _markdown_headings(text: str) -> tuple[MarkdownHeading, ...]:
    """Parse headings while ignoring fenced code blocks.

    Imported card prose does not normally contain code, but honoring fences
    prevents a heading-shaped example from becoming a false section.
    """

    headings: list[MarkdownHeading] = []
    fenced = False
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fenced = not fenced
            offset += len(line)
            continue
        if not fenced:
            match = _HEADING_RE.match(line.rstrip("\r\n"))
            if match:
                headings.append(
                    MarkdownHeading(
                        title=match.group("title").strip(),
                        level=len(match.group("marks")),
                        start=offset,
                        end=offset + len(line.rstrip("\r\n")),
                    )
                )
        offset += len(line)
    return tuple(headings)


def find_card_sections(text: str) -> tuple[CardSection, ...]:
    """Return every recognized section occurrence in source order.

    A recognized canonical heading always starts a new canonical section,
    even when it is deeper than the preceding heading.  This handles the
    existing H3 ``作為一個人的特性`` variant without folding it into the
    preceding H2 ``深層含義`` section.
    """

    headings = _markdown_headings(text)
    classified = {heading.start: classify_section_heading(heading.title) for heading in headings}
    sections: list[CardSection] = []
    for index, heading in enumerate(headings):
        key = classified[heading.start]
        if key is None:
            continue
        boundary = len(text)
        for later in headings[index + 1 :]:
            if classified[later.start] is not None or later.level <= heading.level:
                boundary = later.start
                break
        sections.append(
            CardSection(
                key=key,
                heading=heading.title,
                level=heading.level,
                start=heading.start,
                end=boundary,
                content=text[heading.end:boundary].strip(),
            )
        )
    return tuple(sections)


def extract_card_sections(text: str) -> dict[str, str]:
    """Extract a complete, unique, correctly ordered canonical section map.

    ``ValueError`` is raised for missing, duplicate, out-of-order, or empty
    sections.  The returned mapping follows ``CANONICAL_SECTION_KEYS`` order.
    """

    occurrences = find_card_sections(text)
    counts = {key: 0 for key in CANONICAL_SECTION_KEYS}
    for occurrence in occurrences:
        counts[occurrence.key] += 1
    invalid = [f"{key}={counts[key]}" for key in CANONICAL_SECTION_KEYS if counts[key] != 1]
    if invalid:
        raise ValueError("canonical section counts must all equal 1: " + ", ".join(invalid))

    actual_order = tuple(occurrence.key for occurrence in occurrences)
    if actual_order != CANONICAL_SECTION_KEYS:
        raise ValueError(
            "canonical sections are out of order: "
            f"expected {CANONICAL_SECTION_KEYS!r}, found {actual_order!r}"
        )

    result = {occurrence.key: occurrence.content for occurrence in occurrences}
    empty = [key for key in CANONICAL_SECTION_KEYS if not result[key]]
    if empty:
        raise ValueError("canonical sections must not be empty: " + ", ".join(empty))
    return {key: result[key] for key in CANONICAL_SECTION_KEYS}
