# 資料轉換與索引工具

這些工具只使用 Python 標準函式庫。三份 Pages 原稿先由 Pages 匯出成暫存 DOCX；原始 `.pages` 不會被修改，也不會被工具搬動。

## 匯入目前三份原稿

先做唯讀檢查：

```bash
python3 -B scripts/import_pages_docx.py \
  --major-00-05 /private/tmp/tarot_pages_export/docx/major_00_05.docx \
  --major-06-21 /private/tmp/tarot_pages_export/docx/major_06_21.docx \
  --wands-01-14 /private/tmp/tarot_pages_export/docx/wands_01_14.docx \
  --output-root .
```

檢查全綠後，加上 `--write` 才會建立本機檔案。匯入器會先驗證來源雜湊、36 張牌的順序、22 張組合表、462 筆方向式組合及 494 個超連結；任何一項不符就停止，不寫正式檔。

## 建立本機搜尋索引

```bash
python3 -B scripts/build_local_catalog.py --root . --write --update-deck-status
```

輸出：

- `catalog/card-index.json`：78 張牌的統一搜尋入口；已有內容的 36 張會附摘要與關鍵字。
- `catalog/coverage.json`：目前覆蓋率、花色統計與缺少的 42 張牌。

## 驗證本機匯入結果

```bash
python3 -B scripts/validate_local_import.py --root .
```

驗證器會重新檢查 36 張牌的 ID、檔名、frontmatter、單一 H1 與主要語義章節，也會檢查 22 個大秘儀組合檔是否完整形成 462 筆有方向且不含自我配對的關係。

## 公開限制

`catalog/sources.yaml` 目前仍是 `rights_status: unknown`、`publish: false`。牌義全文、組合牌義、匯入報告和本機搜尋索引先留在這個非 Git 工作區；在來源與授權確認前，不得複製進公開 GitHub 倉庫。資料格式、空白模板和不含原文的工具則可以公開。
