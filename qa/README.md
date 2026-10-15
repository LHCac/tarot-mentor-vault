# 品質檢查

`expected-current.yaml` 保存目前應有的牌組範圍與固定規則；`import-report.json` 是本機匯入三份原稿後的機器報告。

`editorial-review-checklist.md` 是可公開的通用人工審核標準。`manual-review-queue.md` 會放實際牌義的待修項目與原文定位，因此在來源授權確認前只留本機。

`editorial-overrides.example.json` 是不含原文的覆寫格式範例；實際校訂放在被 Git 忽略的 `editorial-overrides*.local.json`。可以按用途分層，但每次重新匯入後都要逐份做 dry-run，通過後才依固定順序加 `--write`。

執行：

```bash
python3 -B scripts/validate_local_import.py --root .
python3 -B scripts/lint_editorial_risks.py --root .
```

原始匯入基線由 `import-report.json` 固定保存；校訂後可以移除錯誤來源連結或增加本庫自寫的參考文件，不回寫原始匯入報告。驗證器會把兩者分開計數。

目前內容基線：

- 36 張牌：22 張大秘儀、14 張權杖
- 22 個大秘儀組合檔、462 筆有方向組合
- 231 組無方向牌對，每組都保留兩個方向
- 30 個牌檔外部參考連結、462 個組合資料參考連結；原始匯入時牌檔為 32 個，隱者的兩個錯誤連結已在校訂層移除
- 2 份原稿前言／基礎檔，以及 1 份本庫自寫的對應體系政策

已完成並留有本機覆寫紀錄：

- 權杖前言原稿停在「帶回生活的指」，已依句意補為「帶回生活的指引」。
- 大秘儀前言原稿標題使用「廷牌」，已依同頁「16 張宮廷牌」校正為「宮廷牌」。
- 戀人、力量、隱者已依 Book T 直接星座對應校正，並將元素、守護星明標為星座衍生欄位。

尚待人工處理：

- 所有牌義目前仍為 `draft`，需要逐張校對來源、措辭與高風險主題表達。

來源授權未確認前，`import-report.json` 與牌義正文都只留本機。
