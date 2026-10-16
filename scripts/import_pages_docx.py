#!/usr/bin/env python3
"""Import the nine reviewed Pages-to-DOCX exports into local Markdown.

The importer is intentionally strict.  It validates the exact reviewed DOCX
exports, card boundaries, card order, directional combination tables, and
hyperlink counts before it writes anything.  The generated card text remains
local while the source rights are marked unknown in catalog/sources.yaml.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable, Sequence
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
W = f"{{{W_NS}}}"


def w(tag: str) -> str:
    return f"{W}{tag}"


@dataclasses.dataclass(frozen=True)
class CardSpec:
    id: str
    path: str
    arcana: str
    suit: str | None
    number: int
    rank: str | None
    name_zh: str
    name_en: str
    slug: str
    source_id: str
    aliases: tuple[str, ...] = ()


MAJOR_DATA = (
    (0, "愚者", "The Fool", "the-fool"),
    (1, "魔術師", "The Magician", "the-magician"),
    (2, "女祭司", "The High Priestess", "the-high-priestess"),
    (3, "皇后", "The Empress", "the-empress"),
    (4, "皇帝", "The Emperor", "the-emperor"),
    (5, "教皇", "The Hierophant", "the-hierophant"),
    (6, "戀人", "The Lovers", "the-lovers"),
    (7, "戰車", "The Chariot", "the-chariot"),
    (8, "力量", "Strength", "strength"),
    (9, "隱者", "The Hermit", "the-hermit"),
    (10, "命運之輪", "Wheel of Fortune", "wheel-of-fortune"),
    (11, "正義", "Justice", "justice"),
    (12, "倒吊人", "The Hanged Man", "the-hanged-man"),
    (13, "死神", "Death", "death"),
    (14, "節制", "Temperance", "temperance"),
    (15, "惡魔", "The Devil", "the-devil"),
    (16, "高塔", "The Tower", "the-tower"),
    (17, "星星", "The Star", "the-star"),
    (18, "月亮", "The Moon", "the-moon"),
    (19, "太陽", "The Sun", "the-sun"),
    (20, "審判", "Judgement", "judgement"),
    (21, "世界", "The World", "the-world"),
)

MAJORS: tuple[CardSpec, ...] = tuple(
    CardSpec(
        id=f"major-{number:02d}-{slug}",
        path=f"knowledge/cards/major-arcana/{number:02d}-{slug}.md",
        arcana="major",
        suit=None,
        number=number,
        rank=None,
        name_zh=name_zh,
        name_en=name_en,
        slug=slug,
        source_id="src-major-00-05" if number <= 5 else "src-major-06-21",
        aliases=("Judgment",) if number == 20 else (("吊人",) if number == 12 else ()),
    )
    for number, name_zh, name_en, slug in MAJOR_DATA
)

WAND_DATA = (
    (1, "ace", "權杖王牌", "Ace of Wands", "ace-of-wands"),
    (2, "two", "權杖二", "Two of Wands", "two-of-wands"),
    (3, "three", "權杖三", "Three of Wands", "three-of-wands"),
    (4, "four", "權杖四", "Four of Wands", "four-of-wands"),
    (5, "five", "權杖五", "Five of Wands", "five-of-wands"),
    (6, "six", "權杖六", "Six of Wands", "six-of-wands"),
    (7, "seven", "權杖七", "Seven of Wands", "seven-of-wands"),
    (8, "eight", "權杖八", "Eight of Wands", "eight-of-wands"),
    (9, "nine", "權杖九", "Nine of Wands", "nine-of-wands"),
    (10, "ten", "權杖十", "Ten of Wands", "ten-of-wands"),
    (11, "page", "權杖侍者", "Page of Wands", "page-of-wands"),
    (12, "knight", "權杖騎士", "Knight of Wands", "knight-of-wands"),
    (13, "queen", "權杖皇后", "Queen of Wands", "queen-of-wands"),
    (14, "king", "權杖國王", "King of Wands", "king-of-wands"),
)

WANDS: tuple[CardSpec, ...] = tuple(
    CardSpec(
        id=f"minor-wands-{number:02d}-{slug}",
        path=f"knowledge/cards/minor-arcana/wands/{number:02d}-{slug}.md",
        arcana="minor",
        suit="wands",
        number=number,
        rank=rank,
        name_zh=name_zh,
        name_en=name_en,
        slug=slug,
        source_id="src-wands-01-14",
    )
    for number, rank, name_zh, name_en, slug in WAND_DATA
)

CUP_DATA = (
    (1, "ace", "聖杯王牌", "Ace of Cups", "ace-of-cups"),
    (2, "two", "聖杯二", "Two of Cups", "two-of-cups"),
    (3, "three", "聖杯三", "Three of Cups", "three-of-cups"),
    (4, "four", "聖杯四", "Four of Cups", "four-of-cups"),
    (5, "five", "聖杯五", "Five of Cups", "five-of-cups"),
    (6, "six", "聖杯六", "Six of Cups", "six-of-cups"),
    (7, "seven", "聖杯七", "Seven of Cups", "seven-of-cups"),
    (8, "eight", "聖杯八", "Eight of Cups", "eight-of-cups"),
    (9, "nine", "聖杯九", "Nine of Cups", "nine-of-cups"),
    (10, "ten", "聖杯十", "Ten of Cups", "ten-of-cups"),
    (11, "page", "聖杯侍者", "Page of Cups", "page-of-cups"),
    (12, "knight", "聖杯騎士", "Knight of Cups", "knight-of-cups"),
    (13, "queen", "聖杯皇后", "Queen of Cups", "queen-of-cups"),
    (14, "king", "聖杯國王", "King of Cups", "king-of-cups"),
)

CUPS: tuple[CardSpec, ...] = tuple(
    CardSpec(
        id=f"minor-cups-{number:02d}-{slug}",
        path=f"knowledge/cards/minor-arcana/cups/{number:02d}-{slug}.md",
        arcana="minor",
        suit="cups",
        number=number,
        rank=rank,
        name_zh=name_zh,
        name_en=name_en,
        slug=slug,
        source_id="src-cups-01-14",
    )
    for number, rank, name_zh, name_en, slug in CUP_DATA
)

SWORD_DATA = (
    (1, "ace", "寶劍王牌", "Ace of Swords", "ace-of-swords"),
    (2, "two", "寶劍二", "Two of Swords", "two-of-swords"),
    (3, "three", "寶劍三", "Three of Swords", "three-of-swords"),
    (4, "four", "寶劍四", "Four of Swords", "four-of-swords"),
    (5, "five", "寶劍五", "Five of Swords", "five-of-swords"),
    (6, "six", "寶劍六", "Six of Swords", "six-of-swords"),
    (7, "seven", "寶劍七", "Seven of Swords", "seven-of-swords"),
    (8, "eight", "寶劍八", "Eight of Swords", "eight-of-swords"),
    (9, "nine", "寶劍九", "Nine of Swords", "nine-of-swords"),
    (10, "ten", "寶劍十", "Ten of Swords", "ten-of-swords"),
    (11, "page", "寶劍侍者", "Page of Swords", "page-of-swords"),
    (12, "knight", "寶劍騎士", "Knight of Swords", "knight-of-swords"),
    (13, "queen", "寶劍皇后", "Queen of Swords", "queen-of-swords"),
    (14, "king", "寶劍國王", "King of Swords", "king-of-swords"),
)

SWORDS: tuple[CardSpec, ...] = tuple(
    CardSpec(
        id=f"minor-swords-{number:02d}-{slug}",
        path=f"knowledge/cards/minor-arcana/swords/{number:02d}-{slug}.md",
        arcana="minor",
        suit="swords",
        number=number,
        rank=rank,
        name_zh=name_zh,
        name_en=name_en,
        slug=slug,
        source_id="src-swords-01-14",
    )
    for number, rank, name_zh, name_en, slug in SWORD_DATA
)

PENTACLE_DATA = (
    (1, "ace", "錢幣王牌", "Ace of Pentacles", "ace-of-pentacles"),
    (2, "two", "錢幣二", "Two of Pentacles", "two-of-pentacles"),
    (3, "three", "錢幣三", "Three of Pentacles", "three-of-pentacles"),
    (4, "four", "錢幣四", "Four of Pentacles", "four-of-pentacles"),
    (5, "five", "錢幣五", "Five of Pentacles", "five-of-pentacles"),
    (6, "six", "錢幣六", "Six of Pentacles", "six-of-pentacles"),
    (7, "seven", "錢幣七", "Seven of Pentacles", "seven-of-pentacles"),
    (8, "eight", "錢幣八", "Eight of Pentacles", "eight-of-pentacles"),
    (9, "nine", "錢幣九", "Nine of Pentacles", "nine-of-pentacles"),
    (10, "ten", "錢幣十", "Ten of Pentacles", "ten-of-pentacles"),
    (11, "page", "錢幣侍者", "Page of Pentacles", "page-of-pentacles"),
    (12, "knight", "錢幣騎士", "Knight of Pentacles", "knight-of-pentacles"),
    (13, "queen", "錢幣皇后", "Queen of Pentacles", "queen-of-pentacles"),
    (14, "king", "錢幣國王", "King of Pentacles", "king-of-pentacles"),
)

PENTACLES: tuple[CardSpec, ...] = tuple(
    CardSpec(
        id=f"minor-pentacles-{number:02d}-{slug}",
        path=f"knowledge/cards/minor-arcana/pentacles/{number:02d}-{slug}.md",
        arcana="minor",
        suit="pentacles",
        number=number,
        rank=rank,
        name_zh=name_zh,
        name_en=name_en,
        slug=slug,
        source_id="src-pentacles-01-14",
    )
    for number, rank, name_zh, name_en, slug in PENTACLE_DATA
)

MAJOR_BY_NUMBER = {card.number: card for card in MAJORS}


@dataclasses.dataclass(frozen=True)
class InputSpec:
    key: str
    source_id: str
    sha256: str
    paragraph_count: int
    nonempty_paragraph_count: int
    table_count: int
    cards: tuple[CardSpec, ...]


INPUT_SPECS = {
    "major_00_05": InputSpec(
        key="major_00_05",
        source_id="src-major-00-05",
        sha256="ceec36a75d722b93bd456a0bebc2d67199e6a5fa727e4120ca978ee0f7ba4d2d",
        paragraph_count=937,
        nonempty_paragraph_count=777,
        table_count=6,
        cards=MAJORS[:6],
    ),
    "major_06_21": InputSpec(
        key="major_06_21",
        source_id="src-major-06-21",
        sha256="b49cd55ef6eec87f5bd705421451b6a9d8eb41f7542befa35cd5496a8e27158c",
        paragraph_count=2477,
        nonempty_paragraph_count=2054,
        table_count=16,
        cards=MAJORS[6:],
    ),
    "wands_01_14": InputSpec(
        key="wands_01_14",
        source_id="src-wands-01-14",
        sha256="bc0843b888c132108b478d6b914de74f77175c99896ae1a47d7b58edfe35a86c",
        paragraph_count=2135,
        nonempty_paragraph_count=1797,
        table_count=0,
        cards=WANDS,
    ),
    "cups_01_14": InputSpec(
        key="cups_01_14",
        source_id="src-cups-01-14",
        sha256="ffebf0286847c9a71dca3f53b6f582c135554a6779f65670327707026756ad99",
        paragraph_count=2365,
        nonempty_paragraph_count=2033,
        table_count=0,
        cards=CUPS,
    ),
    "swords_01_14": InputSpec(
        key="swords_01_14",
        source_id="src-swords-01-14",
        sha256="12fb069d7a5ac5bc12abde46283f4727acf387aa77e1f0370c88c58575481f0d",
        paragraph_count=2170,
        nonempty_paragraph_count=1860,
        table_count=0,
        cards=SWORDS,
    ),
    "pentacles_01_14": InputSpec(
        key="pentacles_01_14",
        source_id="src-pentacles-01-14",
        sha256="43d97111232fad8ab84f17c0719ea1506a7999d91881e671c45c5a71b0749e2a",
        paragraph_count=2173,
        nonempty_paragraph_count=1848,
        table_count=0,
        cards=PENTACLES,
    ),
    "supplemental_guides": InputSpec(
        key="supplemental_guides",
        source_id="src-supplemental-guides",
        sha256="e3c5d48ce3b6182b0266d06544ab3e0351271ed49f991bd90f8875908396d421",
        paragraph_count=232,
        nonempty_paragraph_count=203,
        table_count=1,
        cards=(),
    ),
    "advanced_guides": InputSpec(
        key="advanced_guides",
        source_id="src-advanced-interpretation",
        sha256="60b7428e1e2787f653172cd1f8605b52722c76bdd2399d5a1289aefbd8d28f84",
        paragraph_count=535,
        nonempty_paragraph_count=483,
        table_count=6,
        cards=(),
    ),
    "repeated_messages_guides": InputSpec(
        key="repeated_messages_guides",
        source_id="src-repeated-messages",
        sha256="e44563bc22a8c800614ec441e3e4febdbc07977b0fc9d53ae1fda80d0c6548ca",
        paragraph_count=149,
        nonempty_paragraph_count=127,
        table_count=0,
        cards=(),
    ),
}


@dataclasses.dataclass(frozen=True)
class Link:
    label: str
    url: str


@dataclasses.dataclass(frozen=True)
class Segment:
    text: str
    bold: bool = False
    italic: bool = False
    url: str | None = None


@dataclasses.dataclass(frozen=True)
class Paragraph:
    plain: str
    markdown: str
    max_size: int | None
    bullet: bool
    links: tuple[Link, ...]


@dataclasses.dataclass(frozen=True)
class Cell:
    plain: str
    markdown: str
    links: tuple[Link, ...]


@dataclasses.dataclass(frozen=True)
class Table:
    rows: tuple[tuple[Cell, ...], ...]


@dataclasses.dataclass(frozen=True)
class Block:
    index: int
    kind: str
    value: Paragraph | Table | None


@dataclasses.dataclass(frozen=True)
class Document:
    spec: InputSpec
    path: Path
    blocks: tuple[Block, ...]
    paragraph_count: int
    nonempty_paragraph_count: int
    table_count: int
    link_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xml_bool(element: ET.Element | None) -> bool:
    if element is None:
        return False
    value = element.get(w("val"))
    return value not in {"0", "false", "off"}


def merge_segments(segments: Iterable[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for segment in segments:
        if not segment.text:
            continue
        if (
            merged
            and merged[-1].bold == segment.bold
            and merged[-1].italic == segment.italic
            and merged[-1].url == segment.url
        ):
            previous = merged[-1]
            merged[-1] = Segment(
                previous.text + segment.text,
                previous.bold,
                previous.italic,
                previous.url,
            )
        else:
            merged.append(segment)
    return merged


def formatted_text(text: str, bold: bool, italic: bool) -> str:
    if not text:
        return ""
    leading_match = re.match(r"^\s*", text)
    trailing_match = re.search(r"\s*$", text)
    leading = leading_match.group(0) if leading_match else ""
    trailing = trailing_match.group(0) if trailing_match else ""
    end = len(text) - len(trailing) if trailing else len(text)
    core = text[len(leading) : end]
    if not core:
        return text
    if bold and italic:
        core = f"***{core}***"
    elif bold:
        core = f"**{core}**"
    elif italic:
        core = f"*{core}*"
    return f"{leading}{core}{trailing}"


def markdown_from_segments(segments: Iterable[Segment]) -> str:
    parts: list[str] = []
    for segment in merge_segments(segments):
        if segment.url:
            label = segment.text.replace("[", "\\[").replace("]", "\\]")
            parts.append(f"[{label}]({segment.url})")
        else:
            parts.append(formatted_text(segment.text, segment.bold, segment.italic))
    return "".join(parts).strip()


HYPERLINK_RE = re.compile(r'HYPERLINK\s+"([^"]+)"', re.IGNORECASE)


def parse_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    """Return external hyperlink targets keyed by their document rId."""
    try:
        relationships_xml = archive.read("word/_rels/document.xml.rels")
    except KeyError:
        return {}
    try:
        root = ET.fromstring(relationships_xml)
    except ET.ParseError as error:
        raise ValueError(f"Cannot parse DOCX relationships: {error}") from error

    relationships: dict[str, str] = {}
    for relationship in root.findall(f"./{{{PKG_REL_NS}}}Relationship"):
        relationship_type = relationship.get("Type", "")
        if not relationship_type.endswith("/hyperlink"):
            continue
        relationship_id = relationship.get("Id")
        target = relationship.get("Target")
        if relationship_id and target:
            relationships[relationship_id] = target
    return relationships


def parse_paragraph(
    element: ET.Element,
    relationships: dict[str, str] | None = None,
) -> Paragraph:
    relationships = relationships or {}
    sizes = [
        int(size.get(w("val"), ""))
        for size in element.findall(f".//{w('sz')}")
        if size.get(w("val"), "").isdigit()
    ]
    bullet = element.find(f"./{w('pPr')}/{w('numPr')}") is not None
    segments: list[Segment] = []
    field_links: list[Link] = []
    field: dict[str, object] | None = None

    direct_run_urls: dict[int, str] = {}
    direct_links: list[Link] = []
    for hyperlink in element.iter(w("hyperlink")):
        relationship_id = hyperlink.get(f"{{{R_NS}}}id")
        if not relationship_id:
            # Internal bookmark links use w:anchor and have no relationship.
            continue
        url = relationships.get(relationship_id)
        if url is None:
            raise ValueError(f"Hyperlink relationship {relationship_id!r} is missing")
        label_parts: list[str] = []
        for run in hyperlink.iter(w("r")):
            direct_run_urls[id(run)] = url
            for child in list(run):
                if child.tag == w("t"):
                    label_parts.append(child.text or "")
                elif child.tag == w("tab"):
                    label_parts.append("\t")
                elif child.tag in {w("br"), w("cr")}:
                    label_parts.append("\n")
        label = "".join(label_parts).strip()
        if label:
            direct_links.append(Link(label=label, url=url))

    def append_text(text: str, bold: bool, italic: bool, url: str | None) -> None:
        nonlocal field
        if not text:
            return
        if field is not None:
            phase = field["phase"]
            if phase == "instruction":
                field["instruction"] = str(field["instruction"]) + text
            elif phase == "display":
                display = field["display"]
                assert isinstance(display, list)
                display.append(Segment(text, bold, italic))
            return
        segments.append(Segment(text, bold, italic, url))

    for run in element.iter(w("r")):
        direct_url = direct_run_urls.get(id(run))
        run_properties = run.find(f"./{w('rPr')}")
        bold = xml_bool(run_properties.find(f"./{w('b')}") if run_properties is not None else None)
        italic = xml_bool(run_properties.find(f"./{w('i')}") if run_properties is not None else None)
        for child in list(run):
            if child.tag == w("rPr"):
                continue
            if child.tag == w("fldChar"):
                field_type = child.get(w("fldCharType"))
                if field_type == "begin":
                    if field is not None:
                        raise ValueError("Nested DOCX fields are not supported")
                    field = {"phase": "instruction", "instruction": "", "display": []}
                elif field_type == "separate":
                    if field is None:
                        raise ValueError("Field separator without field start")
                    field["phase"] = "display"
                elif field_type == "end":
                    if field is None:
                        raise ValueError("Field end without field start")
                    instruction = str(field["instruction"])
                    match = HYPERLINK_RE.search(instruction)
                    display_segments = field["display"]
                    assert isinstance(display_segments, list)
                    label = "".join(segment.text for segment in display_segments).strip()
                    if match and label:
                        url = match.group(1).strip()
                        field_links.append(Link(label=label, url=url))
                        segments.append(Segment(label, url=url))
                    elif label:
                        segments.extend(display_segments)
                    field = None
                continue
            if child.tag == w("instrText"):
                if field is None:
                    raise ValueError("Field instruction without field start")
                field["instruction"] = str(field["instruction"]) + (child.text or "")
            elif child.tag == w("t"):
                append_text(child.text or "", bold, italic, direct_url)
            elif child.tag == w("tab"):
                append_text("\t", bold, italic, direct_url)
            elif child.tag in {w("br"), w("cr")}:
                append_text("\n", bold, italic, direct_url)

    if field is not None:
        raise ValueError("Unclosed DOCX field")

    merged = merge_segments(segments)
    plain = "".join(segment.text for segment in merged).strip()
    return Paragraph(
        plain=plain,
        markdown=markdown_from_segments(merged),
        max_size=max(sizes) if sizes else None,
        bullet=bullet,
        links=tuple(field_links + direct_links),
    )


def parse_cell(
    element: ET.Element,
    relationships: dict[str, str] | None = None,
) -> Cell:
    relationships = relationships or {}
    paragraphs = [
        parse_paragraph(paragraph, relationships)
        for paragraph in element.findall(f"./{w('p')}")
    ]
    nonempty = [paragraph for paragraph in paragraphs if paragraph.plain]
    return Cell(
        plain="\n".join(paragraph.plain for paragraph in nonempty),
        markdown="<br>".join(paragraph.markdown for paragraph in nonempty),
        links=tuple(link for paragraph in paragraphs for link in paragraph.links),
    )


def parse_table(
    element: ET.Element,
    relationships: dict[str, str] | None = None,
) -> Table:
    relationships = relationships or {}
    rows: list[tuple[Cell, ...]] = []
    for row in element.findall(f"./{w('tr')}"):
        cells = tuple(
            parse_cell(cell, relationships) for cell in row.findall(f"./{w('tc')}")
        )
        rows.append(cells)
    return Table(rows=tuple(rows))


def parse_document(path: Path, spec: InputSpec, allow_changed_input: bool) -> Document:
    if not path.is_file():
        raise ValueError(f"Input does not exist: {path}")
    actual_hash = sha256_file(path)
    if not allow_changed_input and actual_hash != spec.sha256:
        raise ValueError(
            f"{path.name}: SHA-256 changed; expected {spec.sha256}, got {actual_hash}. "
            "Review the new export before importing it."
        )
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
            relationships = parse_relationships(archive)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as error:
        raise ValueError(f"Cannot parse DOCX {path}: {error}") from error

    body = root.find(f"./{w('body')}")
    if body is None:
        raise ValueError(f"{path.name}: document body is missing")
    blocks: list[Block] = []
    paragraph_count = 0
    nonempty_paragraph_count = 0
    table_count = 0
    link_count = 0
    for index, child in enumerate(list(body)):
        if child.tag == w("p"):
            paragraph = parse_paragraph(child, relationships)
            paragraph_count += 1
            nonempty_paragraph_count += bool(paragraph.plain)
            link_count += len(paragraph.links)
            blocks.append(Block(index=index, kind="paragraph", value=paragraph))
        elif child.tag == w("tbl"):
            table = parse_table(child, relationships)
            table_count += 1
            link_count += sum(len(cell.links) for row in table.rows for cell in row)
            blocks.append(Block(index=index, kind="table", value=table))
        elif child.tag == w("sectPr"):
            blocks.append(Block(index=index, kind="section", value=None))
        else:
            raise ValueError(f"{path.name}: unsupported body element {child.tag}")

    expected_counts = (
        spec.paragraph_count,
        spec.nonempty_paragraph_count,
        spec.table_count,
    )
    actual_counts = (paragraph_count, nonempty_paragraph_count, table_count)
    if not allow_changed_input and actual_counts != expected_counts:
        raise ValueError(
            f"{path.name}: structure changed; expected p/nonempty/table {expected_counts}, "
            f"got {actual_counts}"
        )
    return Document(
        spec=spec,
        path=path,
        blocks=tuple(blocks),
        paragraph_count=paragraph_count,
        nonempty_paragraph_count=nonempty_paragraph_count,
        table_count=table_count,
        link_count=link_count,
    )


def is_card_start(block: Block) -> bool:
    if block.kind != "paragraph":
        return False
    paragraph = block.value
    assert isinstance(paragraph, Paragraph)
    return (
        "\n" not in paragraph.plain
        and len(paragraph.plain) <= 120
        and "牌義解析：" in paragraph.plain
        and "正逆位" in paragraph.plain
    )


def minor_title_prefixes(card: CardSpec) -> tuple[str, ...]:
    prefixes = [f"{card.name_zh}牌義解析：{card.name_en} 正逆位"]
    if card.name_zh.endswith("牌"):
        prefixes.append(f"{card.name_zh}義解析：{card.name_en} 正逆位")
    return tuple(prefixes)


def validate_start_title(paragraph: Paragraph, card: CardSpec) -> None:
    if card.arcana == "major":
        match = re.match(r"^(\d{1,2})\s+(.+?)牌義解析：(.+?)\s+正逆位", paragraph.plain)
        if not match:
            raise ValueError(f"Bad major card title: {paragraph.plain}")
        number, name_zh, name_en = int(match.group(1)), match.group(2), match.group(3)
        if (number, name_zh, name_en) != (card.number, card.name_zh, card.name_en):
            raise ValueError(
                f"Major title mismatch for {card.id}: {(number, name_zh, name_en)}"
            )
    else:
        if not paragraph.plain.startswith(minor_title_prefixes(card)):
            raise ValueError(
                f"Minor card title mismatch for {card.id}: {paragraph.plain!r}"
            )


def start_title_matches_card(paragraph: Paragraph, card: CardSpec) -> bool:
    if card.arcana == "major":
        match = re.match(r"^(\d{1,2})\s+(.+?)牌義解析：(.+?)\s+正逆位", paragraph.plain)
        if not match:
            return False
        return (int(match.group(1)), match.group(2), match.group(3)) == (
            card.number,
            card.name_zh,
            card.name_en,
        )
    return paragraph.plain.startswith(minor_title_prefixes(card))


def split_document(document: Document) -> tuple[tuple[Block, ...], list[tuple[CardSpec, tuple[Block, ...]]]]:
    positions: list[int] = []
    for card in document.spec.cards:
        candidates = [
            index
            for index, block in enumerate(document.blocks)
            if is_card_start(block)
            and isinstance(block.value, Paragraph)
            and start_title_matches_card(block.value, card)
        ]
        if not candidates:
            raise ValueError(f"{document.path.name}: missing card start for {card.id}")
        # Some older Pages exports repeat the article title inside a card.
        # The true boundary is the largest title instance, regardless of the
        # absolute point size used by that particular export.
        largest_size = max(
            (document.blocks[index].value.max_size or -1)  # type: ignore[union-attr]
            for index in candidates
        )
        largest_candidates = [
            index
            for index in candidates
            if isinstance(document.blocks[index].value, Paragraph)
            and (document.blocks[index].value.max_size or -1) == largest_size
        ]
        if len(largest_candidates) != 1:
            raise ValueError(
                f"{document.path.name}: ambiguous card start for {card.id}: "
                f"{largest_candidates}"
            )
        positions.append(largest_candidates[0])
    if not positions:
        return document.blocks, []
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        raise ValueError(f"{document.path.name}: card starts are out of order")
    spans: list[tuple[CardSpec, tuple[Block, ...]]] = []
    for card_index, (position, card) in enumerate(zip(positions, document.spec.cards)):
        paragraph = document.blocks[position].value
        assert isinstance(paragraph, Paragraph)
        validate_start_title(paragraph, card)
        end = positions[card_index + 1] if card_index + 1 < len(positions) else len(document.blocks)
        spans.append((card, document.blocks[position:end]))
    return document.blocks[: positions[0]], spans


SEPARATOR_RE = re.compile(r"^[—–─－﹣\-_]{10,}$")


def is_separator(text: str) -> bool:
    return bool(SEPARATOR_RE.fullmatch(re.sub(r"\s+", "", text)))


def normalize_title(text: str) -> str:
    return re.sub(r"^\d{1,2}\s+", "", text.strip())


def next_nonempty_paragraph(blocks: Sequence[Block], start: int) -> Paragraph | None:
    for block in blocks[start:]:
        if block.kind != "paragraph":
            continue
        paragraph = block.value
        assert isinstance(paragraph, Paragraph)
        if paragraph.plain and not is_separator(paragraph.plain):
            return paragraph
    return None


def extract_summary(blocks: Sequence[Block]) -> str:
    paragraphs = [
        block.value
        for block in blocks
        if block.kind == "paragraph" and isinstance(block.value, Paragraph)
    ]
    for index, paragraph in enumerate(paragraphs):
        if "牌義快速摘要" in paragraph.plain:
            for candidate in paragraphs[index + 1 :]:
                if candidate.plain:
                    return candidate.plain
    for paragraph in paragraphs[1:]:
        if paragraph.plain and paragraph.max_size not in {68, 56, 42, 76}:
            return paragraph.plain
    raise ValueError("Card summary could not be extracted")


def split_keywords(text: str) -> list[str]:
    text = re.sub(r"^(正位|逆位)(關鍵字|關鍵詞|重點)\s*[:：]?\s*", "", text).strip()
    values = [part.strip(" 。.") for part in re.split(r"[、，,；;]", text)]
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def extract_keywords(blocks: Sequence[Block], orientation: str) -> list[str]:
    paragraphs = [
        block.value
        for block in blocks
        if block.kind == "paragraph" and isinstance(block.value, Paragraph)
    ]
    detailed = re.compile(rf"^{orientation}(關鍵字|關鍵詞)\s*[:：]")
    for paragraph in paragraphs:
        if detailed.match(paragraph.plain):
            return split_keywords(paragraph.plain)
    label = f"{orientation}重點"
    for index, paragraph in enumerate(paragraphs):
        if paragraph.plain == label:
            for candidate in paragraphs[index + 1 :]:
                if candidate.plain:
                    return split_keywords(candidate.plain)
    raise ValueError(f"Missing {orientation} keyword source")


def extract_correspondences(blocks: Sequence[Block]) -> dict[str, str | None]:
    keys = {
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
    result: dict[str, str | None] = {
        "element": None,
        "planet": None,
        "zodiac": None,
        "timing": None,
    }
    for block in blocks:
        if block.kind != "paragraph":
            continue
        paragraph = block.value
        assert isinstance(paragraph, Paragraph)
        # Pages may store several visually separate lines in one DOCX
        # paragraph by using explicit line breaks.  Parse every logical line;
        # otherwise only the first label (often "關鍵詞") is seen and the
        # following element/planet/zodiac/timing values are silently lost.
        for line in paragraph.plain.splitlines():
            match = re.match(r"^([^：:]+)\s*[：:]\s*(.+)$", line.strip())
            if not match:
                continue
            output_key = keys.get(match.group(1).strip())
            if output_key and result[output_key] is None:
                result[output_key] = match.group(2).strip()
    return result


def yaml_value(value: object) -> str:
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def frontmatter(card: CardSpec, blocks: Sequence[Block]) -> str:
    correspondences = extract_correspondences(blocks)
    lines = [
        "---",
        "schema_version: 1",
        f"id: {yaml_value(card.id)}",
        'deck_system: "rider-waite-smith"',
        f"arcana: {yaml_value(card.arcana)}",
        f"suit: {yaml_value(card.suit)}",
        f"number: {card.number}",
        f"rank: {yaml_value(card.rank)}",
        f"name_zh: {yaml_value(card.name_zh)}",
        f"name_en: {yaml_value(card.name_en)}",
        f"aliases: {yaml_value(list(card.aliases))}",
        f"keywords_upright: {yaml_value(extract_keywords(blocks, '正位'))}",
        f"keywords_reversed: {yaml_value(extract_keywords(blocks, '逆位'))}",
        "correspondences:",
        f"  element: {yaml_value(correspondences['element'])}",
        f"  planet: {yaml_value(correspondences['planet'])}",
        f"  zodiac: {yaml_value(correspondences['zodiac'])}",
        f"  timing: {yaml_value(correspondences['timing'])}",
        f"summary: {yaml_value(extract_summary(blocks))}",
        f"source_ids: {yaml_value([card.source_id])}",
        'review_status: "draft"',
        "last_reviewed: null",
        "---",
    ]
    return "\n".join(lines)


SUMMARY_LABELS = {"正位重點", "逆位重點", "感情提醒", "工作提醒"}
COMBINATION_HEADING_RE = re.compile(r"組合牌義.*(其他|搭配)")
MAIN_SECTION_RE = re.compile(
    r"(牌義快速摘要$|是什麼[？?]$|關鍵特徵$|^牌面描述$|^牌面象徵解析$|^深層含義$|"
    r"人物特質|(?:正位|逆位)牌義.*整體解讀|牌陣.*(?:解讀|解釋)|是(?:或|／|/)否|"
    r"Yes\s*(?:or|/|／)\s*No|初學者.*(?:誤解|牌義)|常見問題|FAQ|Q&A)",
    re.IGNORECASE,
)


def render_paragraph(
    paragraph: Paragraph,
    foundation: bool = False,
    card: CardSpec | None = None,
    bullet_override: bool | None = None,
) -> str:
    text = paragraph.markdown
    plain = paragraph.plain
    if not plain:
        return ""
    if plain in SUMMARY_LABELS:
        return f"### {plain}"
    # Section keywords can also occur inside complete answer paragraphs (for
    # example, "在是或否的占卜問題中…").  A sentence ending in a
    # full stop is prose, not a heading, even when it contains such a keyword.
    explicit_main_section = (
        "\n" not in plain
        and len(plain) <= 80
        and not plain.endswith(("。", "！", "!"))
        and MAIN_SECTION_RE.search(plain) is not None
    )
    if not foundation and explicit_main_section:
        return f"## {plain}"
    if card is not None and card.suit in {"cups", "swords", "pentacles"}:
        if paragraph.max_size == 51:
            return f"## {plain}"
        if paragraph.max_size == 42:
            return f"### {plain}"
        if paragraph.max_size == 36:
            level = "####" if plain in {"單身者", "有伴侶者"} else "###"
            return f"{level} {plain}"

    render_as_bullet = paragraph.bullet if bullet_override is None else bullet_override
    if render_as_bullet:
        return f"- {text.replace(chr(10), chr(10) + '  ')}"
    if paragraph.max_size in {68, 42}:
        return f"{'###' if foundation else '##'} {plain}"
    if paragraph.max_size == 56:
        return f"{'####' if foundation else '###'} {plain}"
    if foundation and paragraph.max_size in {40, 48, 50}:
        return f"## {plain}"
    return text


CUPS_EXCLUDED_PARAGRAPH_PREFIXES = (
    "塔羅牌 78 張總表",
    "想完整收藏聖杯侍者牌義與 78 張牌義？",
    "這篇屬於付費牌義內容",
)


def is_excluded_card_paragraph(card: CardSpec, paragraph: Paragraph) -> bool:
    return card.source_id == "src-cups-01-14" and any(
        paragraph.plain.startswith(prefix)
        for prefix in CUPS_EXCLUDED_PARAGRAPH_PREFIXES
    )


def append_block(output: list[str], rendered: str) -> None:
    if not rendered:
        if output and output[-1] != "":
            output.append("")
        return
    if output and output[-1] != "":
        output.append("")
    output.append(rendered)


def combination_path(card: CardSpec) -> str:
    return f"knowledge/combinations/major-arcana/{card.number:02d}-{card.slug}.md"


def render_card(card: CardSpec, blocks: Sequence[Block]) -> str:
    first = blocks[0].value
    assert isinstance(first, Paragraph)
    source_title = normalize_title(first.plain)
    output = [
        frontmatter(card, blocks),
        "",
        f"# {card.name_zh}｜{card.name_en}",
        "",
        f"> 本檔由 `{card.source_id}` 匯入，尚待人工校對；內容不確定時請回查來源。",
    ]
    combination_inserted = False
    ace_metadata_labels: set[str] = set()
    ace_metadata_expected = {"關鍵詞", "元素", "行星", "星座", "關鍵日期"}
    for block_index, block in enumerate(blocks):
        if block_index == 0 or block.kind == "section":
            continue
        if block.kind == "table":
            if card.arcana != "major":
                raise ValueError(f"Unexpected table in {card.id}")
            relative = f"../../combinations/major-arcana/{card.number:02d}-{card.slug}.md"
            append_block(output, "## 組合牌義")
            append_block(output, f"請參閱[以{card.name_zh}為主牌的方向式組合資料]({relative})。")
            combination_inserted = True
            continue
        paragraph = block.value
        assert isinstance(paragraph, Paragraph)
        if is_excluded_card_paragraph(card, paragraph):
            continue
        if is_separator(paragraph.plain):
            continue
        if normalize_title(paragraph.plain) == source_title and "牌義解析：" in paragraph.plain:
            continue
        if COMBINATION_HEADING_RE.search(paragraph.plain):
            continue
        bullet_override: bool | None = None
        if card.id == "minor-cups-01-ace-of-cups":
            # The export accidentally carries list formatting through most
            # of this article.  Preserve only the first occurrence of each
            # of the five intended metadata fields.
            bullet_override = False
            label_match = re.match(r"^([^：:]+)\s*[:：]", paragraph.plain)
            if label_match:
                label = label_match.group(1).strip()
                if label in ace_metadata_expected and label not in ace_metadata_labels:
                    ace_metadata_labels.add(label)
                    bullet_override = True
        append_block(
            output,
            render_paragraph(
                paragraph,
                card=card,
                bullet_override=bullet_override,
            ),
        )
    if card.arcana == "major" and not combination_inserted:
        raise ValueError(f"Missing combination table placeholder in {card.id}")
    if card.id == "minor-cups-01-ace-of-cups" and ace_metadata_labels != ace_metadata_expected:
        raise ValueError(
            f"{card.id}: missing Ace metadata bullets: "
            f"{sorted(ace_metadata_expected - ace_metadata_labels)}"
        )
    while output and output[-1] == "":
        output.pop()
    return "\n".join(output) + "\n"


def escape_table_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>").strip()


def extract_combination_rows(card: CardSpec, blocks: Sequence[Block]) -> list[tuple[CardSpec, str, str]]:
    tables = [block.value for block in blocks if block.kind == "table"]
    if len(tables) != 1 or not isinstance(tables[0], Table):
        raise ValueError(f"{card.id}: expected exactly one combination table")
    table = tables[0]
    if len(table.rows) != 22 or any(len(row) != 2 for row in table.rows):
        raise ValueError(f"{card.id}: combination table must be 22x2")
    header = tuple(cell.plain.strip() for cell in table.rows[0])
    if header != ("卡牌", "組合意義"):
        raise ValueError(f"{card.id}: bad combination header {header}")
    rows: list[tuple[CardSpec, str, str]] = []
    seen: set[int] = set()
    for row in table.rows[1:]:
        target_cell, meaning_cell = row
        match = re.match(r"^(\d{1,2})\s", target_cell.plain)
        if not match:
            raise ValueError(f"{card.id}: cannot read target from {target_cell.plain!r}")
        target_number = int(match.group(1))
        if target_number not in MAJOR_BY_NUMBER:
            raise ValueError(f"{card.id}: target {target_number} is not a major card")
        if target_number == card.number or target_number in seen:
            raise ValueError(f"{card.id}: duplicate/self target {target_number}")
        if not meaning_cell.plain:
            raise ValueError(f"{card.id}: empty combination meaning for {target_number}")
        if len(target_cell.links) != 1:
            raise ValueError(
                f"{card.id}: expected one source link for target {target_number}, got {len(target_cell.links)}"
            )
        seen.add(target_number)
        rows.append((MAJOR_BY_NUMBER[target_number], meaning_cell.markdown, target_cell.links[0].url))
    expected = set(MAJOR_BY_NUMBER) - {card.number}
    if seen != expected:
        raise ValueError(f"{card.id}: target set mismatch; missing={sorted(expected-seen)} extra={sorted(seen-expected)}")
    return rows


def render_combination_file(card: CardSpec, rows: Sequence[tuple[CardSpec, str, str]]) -> str:
    output = [
        "---",
        "schema_version: 1",
        f"id: {yaml_value(f'combination-{card.id}')}",
        'deck_system: "rider-waite-smith"',
        f"source_card_id: {yaml_value(card.id)}",
        "directional: true",
        f"source_ids: {yaml_value([card.source_id])}",
        'review_status: "draft"',
        "last_reviewed: null",
        "---",
        "",
        f"# {card.name_zh}為主牌的組合牌義",
        "",
        "> 這是有方向的資料：本頁只代表「主牌 → 搭配牌」。反向解讀請查看另一張主牌的檔案。內容尚待人工校對。",
        "",
        "| 搭配牌 ID | 搭配牌 | 組合意義 | 原始參考 |",
        "|---|---|---|---|",
    ]
    for target, meaning, url in rows:
        label = f"{target.number} {target.name_zh}｜{target.name_en}"
        output.append(
            "| "
            + " | ".join(
                [
                    target.id,
                    escape_table_cell(label),
                    escape_table_cell(meaning),
                    f"[連結]({url})",
                ]
            )
            + " |"
        )
    return "\n".join(output) + "\n"


def render_foundation(
    title: str,
    source_id: str,
    blocks: Sequence[Block],
    warnings: Sequence[str],
) -> str:
    output = [
        "---",
        "schema_version: 1",
        f"source_ids: {yaml_value([source_id])}",
        'review_status: "draft"',
        "last_reviewed: null",
        "---",
        "",
        f"# {title}",
        "",
        f"> 本檔由 `{source_id}` 的牌卡前言匯入，尚待人工校對。",
    ]
    for warning in warnings:
        append_block(output, f"> TODO：{warning}")
    for block in blocks:
        if block.kind == "section":
            continue
        if block.kind == "table":
            raise ValueError(f"Unexpected table in foundation preamble {source_id}")
        paragraph = block.value
        assert isinstance(paragraph, Paragraph)
        if is_separator(paragraph.plain):
            continue
        append_block(output, render_paragraph(paragraph, foundation=True))
    while output and output[-1] == "":
        output.pop()
    return "\n".join(output) + "\n"


def render_generic_table(table: Table) -> str:
    if not table.rows:
        raise ValueError("Supplemental guide contains an empty table")
    width = len(table.rows[0])
    if width == 0 or any(len(row) != width for row in table.rows):
        raise ValueError("Supplemental guide table has inconsistent row widths")
    rows: list[str] = []
    for row_index, row in enumerate(table.rows):
        cells = [escape_table_cell(cell.markdown) for cell in row]
        rows.append("| " + " | ".join(cells) + " |")
        if row_index == 0:
            rows.append("|" + "|".join("---" for _ in cells) + "|")
    return "\n".join(rows)


def render_source_paragraph(paragraph: Paragraph) -> str:
    if not paragraph.plain:
        return ""
    if paragraph.bullet:
        return f"- {paragraph.markdown.replace(chr(10), chr(10) + '  ')}"
    if paragraph.max_size in {48, 51, 57}:
        return f"## {paragraph.plain}"
    if paragraph.max_size in {30, 32, 36, 42}:
        return f"### {paragraph.plain}"
    if paragraph.max_size in {21, 27} and re.match(r"^(Q\d|學習順序)", paragraph.plain):
        return f"#### {paragraph.plain}"
    return paragraph.markdown


def render_source_guide(
    title: str,
    source_id: str,
    blocks: Sequence[Block],
    warnings: Sequence[str] = (),
) -> str:
    output = [
        "---",
        "schema_version: 1",
        f"source_ids: {yaml_value([source_id])}",
        'review_status: "draft"',
        "last_reviewed: null",
        "---",
        "",
        f"# {title}",
        "",
        f"> 本檔由 `{source_id}` 匯入，尚待人工校對；來源權利未確認，僅供本機整理。",
    ]
    for warning in warnings:
        append_block(output, f"> TODO：{warning}")
    for block in blocks:
        if block.kind == "section":
            continue
        if block.kind == "table":
            assert isinstance(block.value, Table)
            append_block(output, render_generic_table(block.value))
            continue
        paragraph = block.value
        assert isinstance(paragraph, Paragraph)
        if is_separator(paragraph.plain):
            continue
        append_block(output, render_source_paragraph(paragraph))
    while output and output[-1] == "":
        output.pop()
    return "\n".join(output) + "\n"


def split_supplemental_guides(blocks: Sequence[Block]) -> dict[str, tuple[Block, ...]]:
    anchors = {
        "basics": "查塔羅牌牌義前，先掌握 3 個重點",
        "reversed": "塔羅牌解牌時，你可能會遇到一種狀況",
        "questions": "塔羅牌怎麼問問題？ 5種常見問法與修改建議",
        "major_life": "塔羅牌的 78 張牌中，大阿爾克那",
        "first_reading": "第一次抽塔羅，腦中常有很多問號",
    }
    positions: dict[str, int] = {}
    for key, prefix in anchors.items():
        matches = [
            index
            for index, block in enumerate(blocks)
            if block.kind == "paragraph"
            and isinstance(block.value, Paragraph)
            and block.value.plain.startswith(prefix)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Supplemental guide anchor {key!r} expected once, got {matches}"
            )
        positions[key] = matches[0]
    order = ["basics", "reversed", "questions", "major_life", "first_reading"]
    ordered_positions = [positions[key] for key in order]
    if ordered_positions != sorted(ordered_positions):
        raise ValueError("Supplemental guide anchors are out of order")
    result: dict[str, tuple[Block, ...]] = {}
    for index, key in enumerate(order):
        start = positions[key]
        end = positions[order[index + 1]] if index + 1 < len(order) else len(blocks)
        result[key] = tuple(blocks[start:end])
    return result


def split_advanced_guides(blocks: Sequence[Block]) -> dict[str, tuple[Block, ...]]:
    anchors = {
        "roadmap": "塔羅牌進階解讀教學總整理",
        "numerology": "小阿爾克那數字意義解析",
        "court_method": "在塔羅牌的 78 張卡片中，16 張宮廷卡",
        "court_profiles": "塔羅中的宮廷牌總共有 16 張",
        "reversed_foundations": "有些人很怕逆位",
        "reversed_advanced": "塔羅逆位代表什麼？先回到正位核心",
        "reversed_quick": "塔羅牌逆位怎麼讀？先用三步驟判斷",
        "timing_methods": "在塔羅占卜中，「什麼時候？」",
        "time_flow": "塔羅時間流解讀不是單純",
    }
    positions: dict[str, int] = {}
    for key, prefix in anchors.items():
        matches = [
            index
            for index, block in enumerate(blocks)
            if block.kind == "paragraph"
            and isinstance(block.value, Paragraph)
            and block.value.plain.startswith(prefix)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Advanced guide anchor {key!r} expected once, got {matches}"
            )
        positions[key] = matches[0]
    order = [
        "roadmap",
        "numerology",
        "court_method",
        "court_profiles",
        "reversed_foundations",
        "reversed_advanced",
        "reversed_quick",
        "timing_methods",
        "time_flow",
    ]
    ordered_positions = [positions[key] for key in order]
    if ordered_positions != sorted(ordered_positions):
        raise ValueError("Advanced guide anchors are out of order")
    result: dict[str, tuple[Block, ...]] = {}
    for index, key in enumerate(order):
        start = positions[key]
        end = positions[order[index + 1]] if index + 1 < len(order) else len(blocks)
        result[key] = tuple(blocks[start:end])
    return result


def remove_advanced_court_promotion(
    blocks: Sequence[Block],
) -> tuple[tuple[Block, ...], int]:
    start_matches = [
        index
        for index, block in enumerate(blocks)
        if block.kind == "paragraph"
        and isinstance(block.value, Paragraph)
        and block.value.plain.startswith("推薦閱讀｜想深入理解宮廷牌")
    ]
    end_matches = [
        index
        for index, block in enumerate(blocks)
        if block.kind == "paragraph"
        and isinstance(block.value, Paragraph)
        and block.value.plain.startswith("宮廷卡確實是塔羅牌中最難掌握")
    ]
    if len(start_matches) != 1 or len(end_matches) != 1:
        raise ValueError(
            "Advanced court promotion boundaries changed: "
            f"start={start_matches}, end={end_matches}"
        )
    start, end = start_matches[0], end_matches[0]
    if start >= end:
        raise ValueError("Advanced court promotion boundaries are out of order")
    excluded = blocks[start:end]
    excluded_links = sum(
        len(block.value.links)
        for block in excluded
        if block.kind == "paragraph" and isinstance(block.value, Paragraph)
    )
    if excluded_links != 1:
        raise ValueError(
            f"Expected one excluded advanced court promotional link, got {excluded_links}"
        )
    return tuple(blocks[:start]) + tuple(blocks[end:]), excluded_links


def split_repeated_messages_guides(
    blocks: Sequence[Block],
) -> dict[str, tuple[Block, ...]]:
    anchors = {
        "recognition": "如何看懂占卜中的重複訊息？",
        "differences": "如何辨識「重複」中真正的差異？",
        "integration": "如何整合重複訊息？",
        "subject_object_foundations": "塔羅主客體解讀指南",
        "subject_object_evidence": "判斷塔羅內在與外在的三個觀察重點",
        "subject_object_casework": "單張牌案例：同一張牌如何因牌位改變主客體？",
        "subject_object_boundaries": "四個常見的塔羅主客體誤讀",
    }
    positions: dict[str, int] = {}
    for key, prefix in anchors.items():
        matches = [
            index
            for index, block in enumerate(blocks)
            if block.kind == "paragraph"
            and isinstance(block.value, Paragraph)
            and block.value.plain.startswith(prefix)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Repeated-message guide anchor {key!r} expected once, got {matches}"
            )
        positions[key] = matches[0]
    order = [
        "recognition",
        "differences",
        "integration",
        "subject_object_foundations",
        "subject_object_evidence",
        "subject_object_casework",
        "subject_object_boundaries",
    ]
    ordered_positions = [positions[key] for key in order]
    if ordered_positions != sorted(ordered_positions):
        raise ValueError("Repeated-message guide anchors are out of order")
    result: dict[str, tuple[Block, ...]] = {}
    for index, key in enumerate(order):
        start = positions[key]
        end = positions[order[index + 1]] if index + 1 < len(order) else len(blocks)
        result[key] = tuple(blocks[start:end])
    return result


def remove_repeated_messages_navigation(
    blocks: Sequence[Block],
) -> tuple[tuple[Block, ...], int]:
    matches = [
        index
        for index, block in enumerate(blocks)
        if block.kind == "paragraph"
        and isinstance(block.value, Paragraph)
        and block.value.plain.startswith("陌生塔羅組合三步驟")
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Repeated-message navigation expected once, got {matches}"
        )
    index = matches[0]
    block = blocks[index]
    assert isinstance(block.value, Paragraph)
    excluded_links = len(block.value.links)
    if excluded_links != 3:
        raise ValueError(
            f"Expected three excluded repeated-message navigation links, got {excluded_links}"
        )
    return tuple(blocks[:index]) + tuple(blocks[index + 1 :]), excluded_links


def build_outputs(documents: Sequence[Document]) -> tuple[dict[str, str], dict[str, object]]:
    outputs: dict[str, str] = {}
    combination_edges: set[tuple[int, int]] = set()
    card_count = 0
    excluded_hyperlinks = 0
    preambles: dict[str, tuple[Block, ...]] = {}
    for document in documents:
        preamble, spans = split_document(document)
        preambles[document.spec.key] = preamble
        for card, blocks in spans:
            excluded_hyperlinks += sum(
                len(block.value.links)
                for block in blocks
                if block.kind == "paragraph"
                and isinstance(block.value, Paragraph)
                and is_excluded_card_paragraph(card, block.value)
            )
            if card.path in outputs:
                raise ValueError(f"Duplicate output path {card.path}")
            outputs[card.path] = render_card(card, blocks)
            card_count += 1
            if card.arcana == "major":
                rows = extract_combination_rows(card, blocks)
                combo_path = combination_path(card)
                outputs[combo_path] = render_combination_file(card, rows)
                for target, _meaning, _url in rows:
                    edge = (card.number, target.number)
                    if edge in combination_edges:
                        raise ValueError(f"Duplicate combination edge {edge}")
                    combination_edges.add(edge)
            elif any(block.kind == "table" for block in blocks):
                raise ValueError(f"Minor card unexpectedly contains a table: {card.id}")

    expected_edges = {(a, b) for a in range(22) for b in range(22) if a != b}
    if combination_edges != expected_edges:
        raise ValueError(
            f"Directional combination coverage mismatch: got {len(combination_edges)}, expected 462"
        )

    outputs["knowledge/foundations/tarot-structure-source.md"] = render_foundation(
        title="塔羅牌架構（原稿前言）",
        source_id="src-major-00-05",
        blocks=preambles["major_00_05"],
        warnings=("原稿寫作「廷牌」，可能是「宮廷牌」的截字；先保留原文。",),
    )
    outputs["knowledge/foundations/minor-arcana-wands-source.md"] = render_foundation(
        title="小秘儀與權杖概覽（原稿前言）",
        source_id="src-wands-01-14",
        blocks=preambles["wands_01_14"],
        warnings=("第二段停在「帶回生活的指」，疑似原稿已截斷；需回原稿人工補字。",),
    )
    outputs["knowledge/foundations/minor-arcana-pentacles-source.md"] = render_foundation(
        title="錢幣牌組概覽（原稿前言）",
        source_id="src-pentacles-01-14",
        blocks=preambles["pentacles_01_14"],
        warnings=(),
    )

    supplemental = split_supplemental_guides(preambles["supplemental_guides"])
    outputs["knowledge/foundations/tarot-reading-basics-source.md"] = render_source_guide(
        title="塔羅牌分類、元素與基礎解讀順序（補充原稿）",
        source_id="src-supplemental-guides",
        blocks=supplemental["basics"],
    )
    outputs["lessons/reversed-cards-source.md"] = render_source_guide(
        title="逆位入門與練習（補充原稿）",
        source_id="src-supplemental-guides",
        blocks=supplemental["reversed"],
        warnings=("原始 DOCX 的兩張愚者正逆位示意圖未匯入文字索引；圖像仍保留於來源檔。",),
    )
    outputs["lessons/question-formulation-source.md"] = render_source_guide(
        title="塔羅提問方式與修改練習（補充原稿）",
        source_id="src-supplemental-guides",
        blocks=supplemental["questions"],
    )
    outputs["lessons/major-arcana-life-guide-source.md"] = render_source_guide(
        title="大秘儀生活對照指南（補充原稿）",
        source_id="src-supplemental-guides",
        blocks=supplemental["major_life"],
    )
    outputs["lessons/first-reading-source.md"] = render_source_guide(
        title="第一次抽牌的五個提醒（補充原稿）",
        source_id="src-supplemental-guides",
        blocks=supplemental["first_reading"],
    )

    advanced = split_advanced_guides(preambles["advanced_guides"])
    advanced_court, advanced_excluded_links = remove_advanced_court_promotion(
        advanced["court_method"]
    )
    excluded_hyperlinks += advanced_excluded_links
    outputs["lessons/advanced-reading-roadmap-source.md"] = render_source_guide(
        title="塔羅牌進階解讀學習路線（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["roadmap"],
        warnings=("原始 DOCX 的第三方文字與圖像權利未確認，全部單元僅供本機整理。",),
    )
    outputs["knowledge/foundations/minor-arcana-numerology-source.md"] = render_source_guide(
        title="小阿爾克那數字與元素（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["numerology"],
        warnings=(
            "原稿含多處疑似錯字與翻譯不順，尚未人工校訂。",
            "原始 DOCX 的 40 張小牌示意圖未放入文字索引；圖像仍保留於來源檔。",
        ),
    )
    outputs["knowledge/foundations/court-card-reading-method-source.md"] = render_source_guide(
        title="宮廷牌角色與解讀方法（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced_court,
        warnings=(
            "原始 DOCX 的 4 張宮廷牌示意圖未放入文字索引；圖像仍保留於來源檔。",
            "一段第三方購物推薦已排除文字索引並保留於本機來源審核表。",
        ),
    )
    outputs["knowledge/foundations/court-card-profiles-source.md"] = render_source_guide(
        title="十六張宮廷牌人物特質（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["court_profiles"],
        warnings=(
            "原稿的性格、職業與性別描述尚待逐項考證；不可當成固定人物、診斷或招聘判定。",
            "原始 DOCX 的 16 張宮廷牌圖未放入文字索引；圖像仍保留於來源檔。",
        ),
    )
    outputs["lessons/reversed-cards-foundations-source.md"] = render_source_guide(
        title="逆位解讀基礎複習（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["reversed_foundations"],
        warnings=("內容與既有逆位入門單元部分重疊，先保留原始分段供日後去重。",),
    )
    outputs["lessons/reversed-cards-advanced-source.md"] = render_source_guide(
        title="逆位進階解讀（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["reversed_advanced"],
        warnings=(
            "內容與其他逆位單元部分重疊，需人工整併與去重。",
            "原始 DOCX 的 2 張正逆位比較圖未放入文字索引；圖像仍保留於來源檔。",
        ),
    )
    outputs["lessons/reversed-cards-quick-reference-source.md"] = render_source_guide(
        title="逆位三步驟快速參考（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["reversed_quick"],
        warnings=("本單元是原稿中的重複快速版，需與完整逆位單元人工整併。",),
    )
    outputs["lessons/timing-methods-source.md"] = render_source_guide(
        title="塔羅計時方法（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["timing_methods"],
        warnings=(
            "牌組、季節、星座與時間單位的對應會因流派而異；不得解讀成確切日期保證。",
        ),
    )
    outputs["lessons/time-flow-reading-source.md"] = render_source_guide(
        title="三張牌時間流解讀（進階原稿）",
        source_id="src-advanced-interpretation",
        blocks=advanced["time_flow"],
        warnings=("時間流只表示目前條件下的可能路徑，不是固定預言。",),
    )

    repeated = split_repeated_messages_guides(
        preambles["repeated_messages_guides"]
    )
    repeated_boundaries, repeated_excluded_links = remove_repeated_messages_navigation(
        repeated["subject_object_boundaries"]
    )
    excluded_hyperlinks += repeated_excluded_links
    outputs["lessons/repeated-messages-recognition-source.md"] = render_source_guide(
        title="重複訊息的辨識與類型（重複訊息原稿）",
        source_id="src-repeated-messages",
        blocks=repeated["recognition"],
        warnings=(
            "重複只表示在當前解讀框架中值得優先檢查的主題，不構成事件必然發生的證據。",
            "原始 DOCX 的牌圖與遠端圖片欄位未放入文字索引。",
        ),
    )
    outputs["lessons/repeated-messages-differences-source.md"] = render_source_guide(
        title="重複訊息中的差異與層次（重複訊息原稿）",
        source_id="src-repeated-messages",
        blocks=repeated["differences"],
        warnings=(
            "相似牌義仍要依牌位、時間順序與可觀察現實分開判斷。",
        ),
    )
    outputs["lessons/repeated-messages-integration-source.md"] = render_source_guide(
        title="重複訊息的整合與案例（重複訊息原稿）",
        source_id="src-repeated-messages",
        blocks=repeated["integration"],
        warnings=(
            "原稿案例含必然性語氣，尚待改寫為有條件的可能路徑。",
            "補充牌可能強化確認偏誤；使用前應先寫明問題與判準。",
        ),
    )
    outputs["knowledge/foundations/subject-object-environment-source.md"] = render_source_guide(
        title="塔羅主體客體與環境（主客體原稿）",
        source_id="src-repeated-messages",
        blocks=repeated["subject_object_foundations"],
        warnings=(
            "主體、客體與環境是解牌焦點，不是固定牌義分類。",
            "涉及他人時只描述可觀察互動，不以牌面當成讀心證據。",
        ),
    )
    outputs["lessons/subject-object-evidence-source.md"] = render_source_guide(
        title="主客體判斷證據與五步驟（主客體原稿）",
        source_id="src-repeated-messages",
        blocks=repeated["subject_object_evidence"],
        warnings=(
            "先以問題與牌位定義角色，再用牌面動作與鄰牌作為可修正的證據。",
        ),
    )
    outputs["lessons/subject-object-casework-source.md"] = render_source_guide(
        title="主客體單牌與三牌案例（主客體原稿）",
        source_id="src-repeated-messages",
        blocks=repeated["subject_object_casework"],
        warnings=(
            "案例用來示範推理方式，不代表可由牌面確認他人動機或現實事件。",
        ),
    )
    outputs["lessons/subject-object-boundaries-faq-source.md"] = render_source_guide(
        title="主客體誤讀界線與常見問題（主客體原稿）",
        source_id="src-repeated-messages",
        blocks=repeated_boundaries,
        warnings=(
            "原稿尾端的三個相關閱讀導流連結已排除文字索引。",
            "涉及他人的結論必須保留現實溝通與事實查證空間。",
        ),
    )

    source_links_total = sum(document.link_count for document in documents)
    if source_links_total != 667:
        raise ValueError(f"Expected 667 source hyperlinks, got {source_links_total}")
    if excluded_hyperlinks != 7:
        raise ValueError(f"Expected 7 excluded hyperlinks, got {excluded_hyperlinks}")
    preserved_links_total = source_links_total - excluded_hyperlinks
    if preserved_links_total != 660:
        raise ValueError(f"Expected 660 preserved hyperlinks, got {preserved_links_total}")
    if card_count != 78:
        raise ValueError(f"Expected 78 cards, got {card_count}")
    combo_file_count = sum(path.startswith("knowledge/combinations/major-arcana/") for path in outputs)
    if combo_file_count != 22:
        raise ValueError(f"Expected 22 combination files, got {combo_file_count}")

    report: dict[str, object] = {
        "schema_version": 1,
        "publish_allowed": False,
        "rights_status": "unknown",
        "cards": {
            "total": 78,
            "major_arcana": 22,
            "wands": 14,
            "cups": 14,
            "swords": 14,
            "pentacles": 14,
        },
        "combination_files": 22,
        "directional_combination_rows": len(combination_edges),
        "undirected_major_pairs": 231,
        "foundation_files": 8,
        "lesson_source_files": 16,
        "source_material_files": 24,
        "advanced_guide_units": 9,
        "advanced_guide_embedded_images": 62,
        "advanced_guide_remote_media_fields": 62,
        "repeated_messages_guide_units": 7,
        "repeated_messages_embedded_images": 12,
        "repeated_messages_image_occurrences": 15,
        "repeated_messages_remote_media_fields": 15,
        "repeated_messages_remote_media_unique_urls": 12,
        "source_hyperlinks_detected": source_links_total,
        "hyperlinks_excluded": excluded_hyperlinks,
        "hyperlinks_preserved": preserved_links_total,
        "source_documents": {
            document.spec.key: {
                "filename": document.path.name,
                "sha256": sha256_file(document.path),
                "paragraphs": document.paragraph_count,
                "nonempty_paragraphs": document.nonempty_paragraph_count,
                "tables": document.table_count,
                "hyperlinks": document.link_count,
            }
            for document in documents
        },
        "warnings": [
            "權杖前言第二段疑似截斷，結尾為「帶回生活的指」。",
            "大秘儀前言的「廷牌」可能應為「宮廷牌」。",
            "聖杯侍者牌尾的導覽與付費推廣共 3 段已排除，其中含 3 個超連結。",
            "補充資料中的 2 張愚者正逆位示意圖保留於原始 DOCX，未放入文字索引。",
            "進階解讀原稿中的 62 張內嵌圖片保留於原始 DOCX，未放入文字索引。",
            "進階解讀原稿的一段第三方購物推薦已排除，其中含 1 個超連結。",
            "進階解讀原稿含疑似錯字、重複內容與待考證對應，九個單元均維持 draft。",
            "重複訊息原稿實際含重複訊息與主客體兩篇文章，已拆成七個本機單元。",
            "重複訊息原稿的 12 張內嵌牌圖、15 次圖片使用與 15 個遠端圖片欄位未放入文字索引。",
            "重複訊息原稿尾端的相關閱讀導流已排除，其中含 3 個超連結。",
            "重複與主客體解讀均維持 draft；不得把重複當作必然證據，也不得以他人牌位代替溝通或查證。",
            "寶劍王牌使用「學習重點」而非日期欄位，因此 timing 保留為 null。",
            "所有匯入內容 review_status 均為 draft，尚待逐張人工校對。",
            "來源權利狀態仍為 unknown，不得推送牌義全文到公開 GitHub。",
        ],
    }
    outputs["qa/import-report.json"] = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if len(outputs) != 125:
        raise ValueError(f"Expected 125 output files, got {len(outputs)}")
    return outputs, report


def write_outputs(root: Path, outputs: dict[str, str]) -> None:
    if (root / ".git").exists():
        raise ValueError(
            "Refusing to write unpublished source text directly into a Git worktree. "
            "Run against a local non-Git staging directory until rights are confirmed."
        )
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".tarot-import-", dir=root))
    try:
        for relative_path, content in sorted(outputs.items()):
            destination = staging / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        for relative_path in sorted(outputs):
            source = staging / relative_path
            destination = root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, destination)
    finally:
        for path in sorted(staging.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        if staging.exists():
            staging.rmdir()


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major-00-05", type=Path, required=True)
    parser.add_argument("--major-06-21", type=Path, required=True)
    parser.add_argument("--wands-01-14", type=Path, required=True)
    parser.add_argument("--cups-01-14", type=Path, required=True)
    parser.add_argument("--swords-01-14", type=Path, required=True)
    parser.add_argument("--pentacles-01-14", type=Path, required=True)
    parser.add_argument("--supplemental-guides", type=Path, required=True)
    parser.add_argument("--advanced-guides", type=Path, required=True)
    parser.add_argument("--repeated-messages-guides", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write validated outputs. Without this flag the importer is check-only.",
    )
    parser.add_argument(
        "--allow-changed-input",
        action="store_true",
        help="Skip reviewed hash/count baselines. Use only after manually reviewing a new export.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    paths = {
        "major_00_05": args.major_00_05,
        "major_06_21": args.major_06_21,
        "wands_01_14": args.wands_01_14,
        "cups_01_14": args.cups_01_14,
        "swords_01_14": args.swords_01_14,
        "pentacles_01_14": args.pentacles_01_14,
        "supplemental_guides": args.supplemental_guides,
        "advanced_guides": args.advanced_guides,
        "repeated_messages_guides": args.repeated_messages_guides,
    }
    try:
        documents = [
            parse_document(paths[key], INPUT_SPECS[key], args.allow_changed_input)
            for key in (
                "major_00_05",
                "major_06_21",
                "wands_01_14",
                "cups_01_14",
                "swords_01_14",
                "pentacles_01_14",
                "supplemental_guides",
                "advanced_guides",
                "repeated_messages_guides",
            )
        ]
        outputs, report = build_outputs(documents)
        if args.write:
            write_outputs(args.output_root.resolve(), outputs)
        result = {
            "ok": True,
            "mode": "write" if args.write else "check-only",
            "output_files": len(outputs),
            **report,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
