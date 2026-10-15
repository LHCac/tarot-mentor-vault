# 牌義人工審核清單

這份清單用於把機器匯入的 `draft` 牌義審核成可供查詢、解牌與教學的 `reviewed` 內容。結構驗證通過只代表沒有缺檔或格式破損，不代表牌義、圖像、占星對應或高風險措辭已經正確。

## 1. 來源與完整性

- 確認檔案對應到正確牌卡，沒有頁尾截斷、漏段、重複或亂碼。
- 原稿、來源登錄與 `source_ids` 相符；引用連結可追溯，宣傳連結不混入正文。
- 公開前確認 `rights_status` 與 `publish`，不因內容已校對就推定可公開。

## 2. 牌組與圖像準確性

- 牌名、牌號、花色、階級及正逆位不相互矛盾。
- 圖像說明确實屬於 frontmatter 指定的牌組系統；不把其他版本的圖像當成 Rider–Waite–Smith 圖像。
- 元素、行星、星座與時間對應需注明使用的體系；與正文不同時先標記待考，不自動擇一。
- 摘要、關鍵詞與正文語義一致，不把只適用特定情境的解釋寫成固定牌義。

## 3. 解讀品質

- 保留多種合理可能，並說明要由問題、牌位、正逆位與其他牌共同判斷。
- 避免「一定」、「保證」、「必然」或把「是／否」當成客觀事實。
- 給出可觀察的現實訊號與可行動的反思步驟，而不是只堆疊同義詞。
- 不代替第三人讀心，不以牌義指控欺騙、犯罪、精神疾病或超自然傷害。

## 4. 高風險主題

- 健康與心理：只能是反思線索，不由牌面判斷病因、診斷、治療、復原或預後；持續或不明症狀要導向合格專業人員。
- 懷孕：可說明孕育象徵，但必須明言塔羅不能驗孕或判定懷孕。
- 財務：牌面不構成投資訊號，不預測收入、報酬、資產成長或風險降低；建議獨立查證並視需要諮詢合格專業人士。
- 法律：不保證公平、判決、合約或訴訟結果，實際權利與期限需由法律專業人士確認。
- 暴力、強迫控制與成癮：不將束縛寫成當事人「自願」或意志力不足；優先支持安全與尋求實際援助。

## 5. 文字與結構

- 使用繁體中文與全庫統一名詞；英文牌名與中文之間留適當空格。
- 每檔只有一個 H1；H2 是主章節，H3 是子題或 FAQ 問題，答案句不當標題。
- 關鍵詞只放短詞；完整建議句移入正文。
- 修正多餘空格、重字、錯字、空章節與不必要的第三方推薦。

## 6. 審核完成條件

只有在上述項目均完成、來源可追溯，且未解決項目已明確標記時，才可將單牌的 `review_status` 改為 `reviewed`，並在 `last_reviewed` 寫入實際審核日期。最後重新執行：

```bash
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.local.json --root .
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.local.json --root . --write
# 若有基礎原稿或牌面考證層，逐份 dry-run 後依序套用；不要用萬用字元改變順序
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.foundation.local.json --root .
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.foundation.local.json --root . --write
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.correspondences.local.json --root .
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.correspondences.local.json --root . --write
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.rws.local.json --root .
python3 -B scripts/apply_editorial_overrides.py qa/editorial-overrides.rws.local.json --root . --write
python3 -B scripts/build_local_catalog.py --root . --write --update-deck-status
python3 -B scripts/validate_local_import.py --root .
python3 -B scripts/lint_editorial_risks.py --root .
```
