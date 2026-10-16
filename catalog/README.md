# 牌組目錄

`deck.yaml` 是 78 張 Rider–Waite–Smith（RWS）牌的唯一目錄，固定每張牌的 ID、檔案路徑、牌名與目前匯入狀態。程式應以它為準，不要從檔名猜測牌序。

## 狀態

- `missing`：目前沒有可匯入的來源。
- `import-planned`：已有本機來源並排入匯入，但正式的一牌一檔尚未通過檢查。
- `draft`：牌卡 Markdown 已建立，仍待人工審核。
- `reviewed`：內容與來源已人工審核，且 `last_reviewed` 已填日期。

目前本機 78 張牌都已建立並通過結構檢查，狀態均為 `draft`。`draft` 只表示機器匯入成功，仍需逐張人工校對後才能改成 `reviewed`。

此狀態描述本機知識工作區；在 `publish: false` 期間，公開 GitHub 鏡像不會包含對應的牌義正文，即使目錄已標示為 `draft`。

## 來源與公開政策

`sources.yaml` 只記錄來源身分、涵蓋範圍與授權狀態。`rights_status: unknown` 且 `publish: false` 表示原文及其衍生牌義不可推送到公開 GitHub；可以公開資料結構、目錄與不含原文的工具。

卡片 frontmatter 的格式由 `schemas/card.schema.json` 定義。缺少的對應資訊一律保留 `null`，不可為了通過檢查自行補寫。

`card-index.json` 會從牌檔正文衍生 `sections`，固定提供 `key_features`、`visual_description`、`symbolism`、`deeper_meaning`、`person_traits` 五個入口。長文仍只保存在 Markdown 正文，不重複塞進 frontmatter。
