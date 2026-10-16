# 資料轉換與索引工具

這些工具只使用 Python 標準函式庫。三份 Pages 原稿先由 Pages 匯出成暫存 DOCX，另直接讀取聖杯、寶劍、錢幣、補充資料、進階解讀與重複訊息六份 DOCX；原始 `.pages`／`.docx` 不會被修改，也不會被工具搬動。

## 匯入目前九份原稿

先做唯讀檢查：

```bash
python3 -B scripts/import_pages_docx.py \
  --major-00-05 /private/tmp/tarot_pages_export/docx/major_00_05.docx \
  --major-06-21 /private/tmp/tarot_pages_export/docx/major_06_21.docx \
  --wands-01-14 /private/tmp/tarot_pages_export/docx/wands_01_14.docx \
  --cups-01-14 "/path/to/聖杯系列.docx" \
  --swords-01-14 "/path/to/寶劍系列.docx" \
  --pentacles-01-14 "/path/to/錢幣牌組.docx" \
  --supplemental-guides "/path/to/補充資料.docx" \
  --advanced-guides "/path/to/塔羅牌進階解讀.docx" \
  --repeated-messages-guides "/path/to/如何看懂占卜中的重複訊息.docx" \
  --output-root .
```

檢查全綠後，加上 `--write` 才會建立本機檔案。匯入器會先驗證來源雜湊、78 張牌的順序、22 張組合表、462 筆方向式組合及 667 個來源超連結；聖杯原稿的 3 個網站導覽／訂閱連結、進階原稿的 1 個購物推薦連結與重複訊息原稿的 3 個導流連結會排除，因此輸出保留 660 個外連。補充資料會拆成 1 份基礎檔與 4 份課程原稿；進階解讀拆成 3 份基礎參考與 6 份課程原稿；重複訊息與主客體則拆成 1 份基礎參考與 6 份課程原稿。補充資料的 2 張圖、進階原稿的 62 張圖，以及重複訊息原稿的 12 張圖與 15 個遠端圖片欄位仍只保留在原始 DOCX。任何一項不符就停止，不寫正式檔。它也會解析 Pages 在同一 DOCX 段落內的手動換行，避免對應資料只擷取到第一行。

## 建立本機搜尋索引

```bash
python3 -B scripts/build_local_catalog.py --root . --write --update-deck-status
```

輸出：

- `catalog/card-index.json`：78 張牌的統一搜尋入口；每張都附摘要、關鍵字與五個標準內容區塊。
- `catalog/coverage.json`：目前覆蓋率、花色統計與缺漏狀態。

## 套用已核准的本機校訂

每次重新匯入會忠實重建牌檔，因此已確認的校訂要放在一個或多個本機 `qa/editorial-overrides*.local.json`，再以固定順序重複套用。可按用途分層，例如依序套用機械性校訂 `editorial-overrides.local.json`、基礎原稿校訂 `editorial-overrides.foundation.local.json`、體系對應校訂 `editorial-overrides.correspondences.local.json`、牌面考證 `editorial-overrides.rws.local.json`，最後套用語義與來源清理 `editorial-overrides.semantics.local.json`。公開的 `qa/editorial-overrides.example.json` 只有虛構格式範例。

先做不寫檔檢查：

```bash
python3 -B scripts/apply_editorial_overrides.py \
  qa/editorial-overrides.local.json --root .
```

所有 `expected_count` 都符合後才套用：

```bash
python3 -B scripts/apply_editorial_overrides.py \
  qa/editorial-overrides.local.json --root . --write
```

若有分層清單，逐份先 dry-run，再依既定順序加上 `--write`。工具會先驗證單一清單的全部覆寫；任一路徑、文字或數量不符時，該批都不寫入。不要用萬用字元一次套用，以免檔案順序因環境而改變。

## 掃描編輯風險

```bash
python3 -B scripts/lint_editorial_risks.py --root .
```

輸出為 JSON，會列出斷言、健康結果、財務結果、懷孕、法律結果、受害者責怪、可疑標題與中文多餘空格。Finding 是人工審核提示，不是自動判錯；只要掃描正常完成，即使有 finding 也會以成功狀態結束。

## 驗證本機匯入結果

```bash
python3 -B scripts/validate_local_import.py --root .
```

驗證器會重新檢查 78 張牌的 ID、檔名、frontmatter、單一 H1 與主要語義章節，並要求「關鍵特徵、牌面描述、牌面象徵解析、深層含義、人物特質」各出現一次且順序固定；同時比對 frontmatter 與正文第一組可見的元素、行星、星座與時間對應。它也會檢查 22 個大秘儀組合檔是否完整形成 462 筆有方向且不含自我配對的關係，並對校訂後的牌檔外連、基礎檔與課程原稿數量做防漂移斷言。

建議的完整順序是：匯入 → 依序套用各層本機覆寫 → 建立索引 → 結構驗證 → 編輯風險掃描。

## 公開限制

`catalog/sources.yaml` 目前仍是 `rights_status: unknown`、`publish: false`。牌義全文、組合牌義、匯入報告和本機搜尋索引先留在這個非 Git 工作區；在來源與授權確認前，不得複製進公開 GitHub 倉庫。資料格式、空白模板和不含原文的工具則可以公開。
