#!/usr/bin/env python3
"""Import the three reviewed Pages-to-DOCX exports into local Markdown.

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


def parse_paragraph(element: ET.Element) -> Paragraph:
    sizes = [
        int(size.get(w("val"), ""))
        for size in element.findall(f".//{w('sz')}")
        if size.get(w("val"), "").isdigit()
    ]
    bullet = element.find(f"./{w('pPr')}/{w('numPr')}") is not None
    segments: list[Segment] = []
    links: list[Link] = []
    field: dict[str, object] | None = None

    def append_text(text: str, bold: bool, italic: bool) -> None:
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
        segments.append(Segment(text, bold, italic))

    for run in element.iter(w("r")):
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
                        links.append(Link(label=label, url=url))
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
                append_text(child.text or "", bold, italic)
            elif child.tag == w("tab"):
                append_text("\t", bold, italic)
            elif child.tag in {w("br"), w("cr")}:
                append_text("\n", bold, italic)

    if field is not None:
        raise ValueError("Unclosed DOCX field")

    merged = merge_segments(segments)
    plain = "".join(segment.text for segment in merged).strip()
    return Paragraph(
        plain=plain,
        markdown=markdown_from_segments(merged),
        max_size=max(sizes) if sizes else None,
        bullet=bullet,
        links=tuple(links),
    )


def parse_cell(element: ET.Element) -> Cell:
    paragraphs = [parse_paragraph(p) for p in element.findall(f"./{w('p')}")]
    nonempty = [paragraph for paragraph in paragraphs if paragraph.plain]
    return Cell(
        plain="\n".join(paragraph.plain for paragraph in nonempty),
        markdown="<br>".join(paragraph.markdown for paragraph in nonempty),
        links=tuple(link for paragraph in paragraphs for link in paragraph.links),
    )


def parse_table(element: ET.Element) -> Table:
    rows: list[tuple[Cell, ...]] = []
    for row in element.findall(f"./{w('tr')}"):
        cells = tuple(parse_cell(cell) for cell in row.findall(f"./{w('tc')}"))
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
            paragraph = parse_paragraph(child)
            paragraph_count += 1
            nonempty_paragraph_count += bool(paragraph.plain)
            link_count += len(paragraph.links)
            blocks.append(Block(index=index, kind="paragraph", value=paragraph))
        elif child.tag == w("tbl"):
            table = parse_table(child)
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
        paragraph.max_size == 76
        and "牌義解析：" in paragraph.plain
        and "正逆位" in paragraph.plain
    )


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
        expected_prefix = f"{card.name_zh}牌義解析：{card.name_en} 正逆位"
        if not paragraph.plain.startswith(expected_prefix):
            raise ValueError(
                f"Wands title mismatch for {card.id}: {paragraph.plain!r}"
            )


def split_document(document: Document) -> tuple[tuple[Block, ...], list[tuple[CardSpec, tuple[Block, ...]]]]:
    positions = [index for index, block in enumerate(document.blocks) if is_card_start(block)]
    if len(positions) != len(document.spec.cards):
        raise ValueError(
            f"{document.path.name}: expected {len(document.spec.cards)} card starts, got {len(positions)}"
        )
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
    r"(牌義快速摘要$|關鍵特徵$|^牌面描述$|^牌面象徵解析$|^深層含義$|"
    r"人物特質|(?:正位|逆位)牌義.*整體解讀|牌陣.*解讀|是(?:或|／|/)否|"
    r"Yes\s*(?:or|/|／)\s*No|初學者.*(?:誤解|牌義)|常見問題|FAQ|Q&A)",
    re.IGNORECASE,
)


def render_paragraph(paragraph: Paragraph, foundation: bool = False) -> str:
    text = paragraph.markdown
    plain = paragraph.plain
    if not plain:
        return ""
    if paragraph.bullet:
        return f"- {text.replace(chr(10), chr(10) + '  ')}"
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
    if paragraph.max_size in {68, 42}:
        return f"{'###' if foundation else '##'} {plain}"
    if paragraph.max_size == 56:
        return f"{'####' if foundation else '###'} {plain}"
    if foundation and paragraph.max_size in {40, 48, 50}:
        return f"## {plain}"
    return text


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
        if is_separator(paragraph.plain):
            continue
        if normalize_title(paragraph.plain) == source_title and "牌義解析：" in paragraph.plain:
            continue
        if COMBINATION_HEADING_RE.search(paragraph.plain):
            continue
        append_block(output, render_paragraph(paragraph))
    if card.arcana == "major" and not combination_inserted:
        raise ValueError(f"Missing combination table placeholder in {card.id}")
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


def build_outputs(documents: Sequence[Document]) -> tuple[dict[str, str], dict[str, object]]:
    outputs: dict[str, str] = {}
    combination_edges: set[tuple[int, int]] = set()
    card_count = 0
    preambles: dict[str, tuple[Block, ...]] = {}
    for document in documents:
        preamble, spans = split_document(document)
        preambles[document.spec.key] = preamble
        for card, blocks in spans:
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

    links_total = sum(document.link_count for document in documents)
    if links_total != 494:
        raise ValueError(f"Expected 494 hyperlinks, got {links_total}")
    if card_count != 36:
        raise ValueError(f"Expected 36 cards, got {card_count}")
    combo_file_count = sum(path.startswith("knowledge/combinations/major-arcana/") for path in outputs)
    if combo_file_count != 22:
        raise ValueError(f"Expected 22 combination files, got {combo_file_count}")

    report: dict[str, object] = {
        "schema_version": 1,
        "publish_allowed": False,
        "rights_status": "unknown",
        "cards": {
            "total": 36,
            "major_arcana": 22,
            "wands": 14,
        },
        "combination_files": 22,
        "directional_combination_rows": len(combination_edges),
        "undirected_major_pairs": 231,
        "foundation_files": 2,
        "hyperlinks_preserved": links_total,
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
            "所有匯入內容 review_status 均為 draft，尚待逐張人工校對。",
            "來源權利狀態仍為 unknown，不得推送牌義全文到公開 GitHub。",
        ],
    }
    outputs["qa/import-report.json"] = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
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
    }
    try:
        documents = [
            parse_document(paths[key], INPUT_SPECS[key], args.allow_changed_input)
            for key in ("major_00_05", "major_06_21", "wands_01_14")
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
