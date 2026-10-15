# 品質檢查

`expected-current.yaml` 保存目前應有的牌組範圍與固定規則；`import-report.json` 是本機匯入三份原稿後的機器報告。

`editorial-review-checklist.md` 是可公開的通用人工審核標準。`manual-review-queue.md` 會放實際牌義的待修項目與原文定位，因此在來源授權確認前只留本機。

`editorial-overrides.example.json` 是不含原文的覆寫格式範例；實際校訂放在被 Git 忽略的 `editorial-overrides*.local.json`。可以按用途分層，但每次重新匯入後都要逐份做 dry-run，通過後才依固定順序加 `--write`。

執行：

```bash
python3 -B scripts/validate_local_import.py --root .
python3 -B scripts/lint_editorial_risks.py --root .
```

目前通過基線：

- 36 張牌：22 張大秘儀、14 張權杖
- 22 個大秘儀組合檔、462 筆有方向組合
- 231 組無方向牌對，每組都保留兩個方向
- 32 個牌檔外部參考連結、462 個組合資料參考連結
- 2 份前言／基礎檔

尚待人工處理：

- 權杖前言有一句停在「帶回生活的指」，疑似原稿已截斷。
- 大秘儀前言使用「廷牌」，可能原意是「宮廷牌」。
- 所有牌義目前仍為 `draft`，需要逐張校對來源、措辭與高風險主題表達。

來源授權未確認前，`import-report.json` 與牌義正文都只留本機。
