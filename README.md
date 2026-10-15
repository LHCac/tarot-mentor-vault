# Tarot Mentor Vault

繁體中文塔羅知識庫，預計支援牌義查詢、單牌與多牌解讀、循序教學，以及 AI 導師式問答。

目前的 36 張牌義只存在本機工作副本；公開 GitHub clone 會刻意只保留資料架構、狀態目錄、工具與導師指南，不包含尚未確認授權的牌義全文或本機索引。

## 本機整理進度

- 大秘儀：22／22，已轉為一牌一檔 `draft`
- 權杖：14／14，已轉為一牌一檔 `draft`
- 大秘儀方向式組合：462／462
- 全牌組：36／78
- 待補：聖杯、寶劍、錢幣，共 42 張

`draft` 表示原稿已完整拆分並通過機器檢查，不等於內容已人工審定。兩處原稿疑點已記入本機的 `qa/import-report.json`，後續校對時處理。

## 如何使用

### 解牌

1. 先從本機的 `catalog/card-index.json` 找到牌卡 ID 與檔案。
2. 單牌基礎解讀查 `knowledge/cards/`；正逆位與問題主題都留在同一張牌檔。
3. 兩張大秘儀同時出現時，再查 `knowledge/combinations/major-arcana/`。組合資料有方向性，A → B 與 B → A 必須分開讀。
4. 依牌陣位置做綜合推論，並區分「原稿明確記載」與「根據牌陣延伸」。

### 教學

依 `lessons/learning-path.md` 從牌組架構、單牌、正逆位、組合牌義到完整牌陣逐步學習。AI 導師的解讀規則在 `mentor/reading-and-teaching-guide.md`，可直接複製的提問方式在 `mentor/query-examples.md`。

## 整理流程

1. 新資料先放入 `inbox/`。
2. 原始檔確認後保存於 `sources/original/`，不直接作為知識庫正文。
3. 牌義轉為 `knowledge/cards/` 下的一牌一檔 Markdown。
4. 組合牌義、牌陣與課程分開保存，避免混入單牌基礎資料。
5. 每筆內容保留來源、版本與審核狀態，讓 AI 能指出依據與不確定處。

## 目錄

- `inbox/`：等待整理的新資料
- `sources/original/`：原始來源檔
- `knowledge/cards/`：78 張牌的標準化內容
- `knowledge/combinations/`：兩張以上的組合牌義
- `knowledge/foundations/`：塔羅基礎、解讀原則與倫理
- `spreads/`：牌陣與位置定義
- `lessons/`：教學順序、練習與測驗
- `glossary/`：統一名詞與中英對照
- `schemas/`：資料格式與內容模板
- `catalog/`：78 張固定目錄、來源登錄與本機搜尋索引
- `qa/`：匯入結果與驗證基線
- `scripts/`：DOCX 轉換、索引與驗證工具
- `mentor/`：AI 導師的回答與安全規則

## 資料政策

原始文件目前不應直接放入公開倉庫。任何非自行撰寫的內容，在公開前都必須補上來源與授權資訊。由於目前三份來源仍標示 `rights_status: unknown`、`publish: false`，牌義全文與本機索引先留在非 Git 工作區；GitHub 只同步資料架構、空白模板與不含原文的工具。健康、財務、法律與心理健康主題只能作為反思提示，不能代替專業建議。
