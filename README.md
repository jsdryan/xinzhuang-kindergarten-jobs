# 新莊區教保員職缺

每天台灣時間 06:30 由家裡 NAS 的 [nas-collector](https://github.com/jsdryan/nas-collector) 執行 `scraper/fetch_jobs.py`（教育部人才庫擋國外 IP，GitHub Actions 抓不到；Actions 只留手動備援），更新 `docs/data.json`，GitHub Pages 由 `docs/` 提供網頁。

- 自動來源：教育部公私立幼兒園人才庫（新北市新莊區）、518 熊班、新北市幼兒教育資源網公告
- 104、1111 有防機器人驗證，不自動抓；網頁提供已篩選條件的即時搜尋連結，`docs/snapshot.json` 是人工整理的清單
- 考試日程（`scraper/fetch_exams.py` → `docs/exams.json`）：新北市幼教網的甄選簡章公告內文、教育部教師資格考試網站；官方未公告的項目用前一年推一年並標「預估」
- 幼教專班（`scraper/fetch_programs.py` → `docs/programs.json`）：各校幼教專班公告頁（清單在 SCHOOLS）、新北市幼教網轉知的全國報名時程
- 篩選：職稱含「教保員」且不是只有「助理教保員」；排除時薪制；人才庫職缺過了報名截止日即隱藏

手動執行：`python3 scraper/fetch_jobs.py`
