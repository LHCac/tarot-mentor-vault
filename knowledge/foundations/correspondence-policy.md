# 大秘儀對應體系政策

本庫在回答元素、行星、星座與時段問題時，必須先說明採用哪一套體系，不把不同流派的對應混成唯一標準答案。

## 預設體系

Rider–Waite–Smith 大秘儀的牌－星座對應，預設採 Hermetic Order of the Golden Dawn 的 Book T 系統。可追溯的公開版本是 1912 年《The Equinox》第一卷第八期〈A Description of the Cards of the Tarot, with their Attributions〉中的對應表。

該歷史表使用 Fortitude 11、Justice 8 的編號；本庫則依 RWS 牌面名稱與牌序，記為 Strength 8、Justice 11，但保留 Strength＝Leo、Justice＝Libra 的牌名對應。

| RWS 大秘儀 | Book T 的直接星座對應 |
|---|---|
| 皇帝 The Emperor | 牡羊座 Aries |
| 教皇 The Hierophant | 金牛座 Taurus |
| 戀人 The Lovers | 雙子座 Gemini |
| 戰車 The Chariot | 巨蟹座 Cancer |
| 力量 Strength | 獅子座 Leo |
| 隱者 The Hermit | 處女座 Virgo |
| 正義 Justice | 天秤座 Libra |
| 死神 Death | 天蠍座 Scorpio |
| 節制 Temperance | 射手座 Sagittarius |
| 惡魔 The Devil | 摩羯座 Capricorn |
| 星星 The Star | 水瓶座 Aquarius |
| 月亮 The Moon | 雙魚座 Pisces |

## 欄位怎麼讀

- `zodiac`：Book T 對這張牌的直接星座歸屬。
- `element`：由該星座的元素延伸；例如雙子座為風、獅子座為火、處女座為土。
- `planet`：由該星座的守護星延伸；例如雙子座與處女座的守護星為水星，獅子座的守護星為太陽。這不是 Book T 對該牌另列的獨立行星歸屬。
- `timing`：只表示對應星座的時段，實際起訖以採用的占星曆為準；不得當成事件一定發生的日期。

若原稿使用其他體系，應保留來源說明並標成待考；未知值使用 `null`，不要用牌面直覺補齊。解牌時，對應資料是輔助觀察，不應凌駕牌位、提問情境與現實證據。

## 參考來源

- [The Equinox, Vol. I, No. VIII（1912），Book T 對應表見 PDF 第 195–197 頁／原刊頁 150–152](https://www.thelemistas.org/PDF/Equinox-Vol_1_No_08.pdf)
- [Astrodienst：星座守護星表](https://www.astro.com/astrowiki/en/Ruler)
- [Astrodienst：星座元素與守護星概覽](https://www.astro.com/astrology/in_signs_e.htm)
