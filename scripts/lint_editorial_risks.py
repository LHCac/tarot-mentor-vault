#!/usr/bin/env python3
"""Report editorial risk signals in local tarot card Markdown.

Findings are review prompts, not validation failures.  A successful scan exits
zero even when it finds many items; only argument or file-reading failures are
errors.  The script is intentionally read-only and uses the standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Sequence


RULES: dict[str, re.Pattern[str]] = {
    "certainty": re.compile(r"一定會|必然|絕對|保證|肯定會|確保|將會"),
    "pregnancy": re.compile(r"懷孕|驗孕|受孕|孕育"),
    "victim_blame": re.compile(
        r"(?:束縛.{0,16}(?:自願|自己選擇|意志力不足))|"
        r"(?:(?:暴力|受害|強迫|控制|成癮).{0,24}(?:自願|意志力|自己負責))"
    ),
    "suspicious_heading": re.compile(
        r"^##\s+(?:在[「『]?是或否|許多塔羅初學者)|^##\s+.{45,}|^##\s+.*[。！!]$"
    ),
    "cjk_spacing": re.compile(r"[\u3400-\u9fff]\s+[\u3400-\u9fff]"),
}
CATEGORY_NAMES = (
    "certainty",
    "health_outcome",
    "financial_outcome",
    "pregnancy",
    "legal_outcome",
    "victim_blame",
    "suspicious_heading",
    "cjk_spacing",
)

HEALTH_CONTEXT = re.compile(
    r"健康|身體|身心|症狀|不適|醫療|治療|疾病|病因|"
    r"免疫|頭痛|肌肉|心理|焦慮|憂鬱|精神|復原|恢復能力"
)
HEALTH_OUTCOME = re.compile(
    r"改善|好轉|恢復|復原|療癒|診斷|治療|預後|導致|"
    r"造成|找到原因|活力|穩定|增強|下降|警訊|正在"
)
FINANCIAL_CONTEXT = re.compile(r"投資|財務|收入|報酬|回報|收益|資產|金錢|理財")
FINANCIAL_OUTCOME = re.compile(
    r"增加|成長|增長|改善|穩定|成果|降低風險|機會|"
    r"獲利|損失|累積|達成|正向|理想"
)
LEGAL_CONTEXT = re.compile(r"法律|訴訟|判決|合約|契約|法院|勝訴|敗訴")
LEGAL_OUTCOME = re.compile(r"結果|公平|公正|確保|保證|會|將|可預期")
FENCE_RE = re.compile(r"^\s*```")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan local card Markdown for editorial review signals."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="knowledge-base root (default: parent of scripts directory)",
    )
    return parser.parse_args(argv)


def excerpt(line: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", line).strip()
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def categories_for_line(line: str) -> list[str]:
    categories = [name for name, pattern in RULES.items() if pattern.search(line)]
    if HEALTH_CONTEXT.search(line) and HEALTH_OUTCOME.search(line):
        categories.append("health_outcome")
    if FINANCIAL_CONTEXT.search(line) and FINANCIAL_OUTCOME.search(line):
        categories.append("financial_outcome")
    if LEGAL_CONTEXT.search(line) and LEGAL_OUTCOME.search(line):
        categories.append("legal_outcome")
    return sorted(set(categories))


def scan_file(path: Path, root: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    findings: list[dict[str, Any]] = []
    in_frontmatter = False
    frontmatter_done = False
    in_fence = False

    for number, line in enumerate(text.splitlines(), start=1):
        if number == 1 and line == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if line == "---":
                in_frontmatter = False
                frontmatter_done = True
            continue
        if not frontmatter_done and line == "---":
            in_frontmatter = True
            continue
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or not line.strip():
            continue

        for category in categories_for_line(line):
            findings.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "line": number,
                    "category": category,
                    "excerpt": excerpt(line),
                }
            )
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve(strict=False)
    card_root = root / "knowledge" / "cards"
    summary: dict[str, Any] = {
        "ok": False,
        "root": str(root),
        "files_scanned": 0,
        "findings_total": 0,
        "counts_by_category": {},
        "findings": [],
        "errors": [],
    }

    if not root.is_dir():
        summary["errors"].append("root must be an existing directory")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    if not card_root.is_dir():
        summary["errors"].append("knowledge/cards directory is missing")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    paths = sorted(
        path
        for path in card_root.rglob("*.md")
        if path.name.casefold() != "readme.md"
    )
    all_findings: list[dict[str, Any]] = []
    for path in paths:
        try:
            all_findings.extend(scan_file(path, root))
        except (OSError, UnicodeError) as exc:
            summary["errors"].append(
                f"{path.relative_to(root).as_posix()}: {exc}"
            )

    counts = Counter(item["category"] for item in all_findings)
    summary["files_scanned"] = len(paths)
    summary["findings_total"] = len(all_findings)
    summary["counts_by_category"] = {
        category: counts.get(category, 0) for category in CATEGORY_NAMES
    }
    summary["findings"] = all_findings
    summary["ok"] = not summary["errors"]
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
