"""每天抓新莊區「教保員」職缺，輸出 docs/data.json。

來源（只抓允許一般程式讀取的公開頁面，不繞過任何防機器人驗證）：
- 教育部 公私立幼兒園人才庫媒合專區（新北市新莊區）
- 518 熊班（教保員／保育員類別、新北市新莊區）
- 新北市幼兒教育資源網 最新公告（只留甄選／招募相關標題）

只用 Python 標準函式庫，GitHub Actions 不必安裝套件。
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TW = timezone(timedelta(hours=8))
UA = "Mozilla/5.0 (compatible; xinzhuang-kindergarten-jobs/1.0; +https://github.com/jsdryan/xinzhuang-kindergarten-jobs)"
OUT = Path(__file__).resolve().parent.parent / "docs" / "data.json"

K12_BASE = "https://hr.k12ea.gov.tw"
K12_LIST = K12_BASE + "/ecehr/JobVacancy/Index?CountyCode=65000&DistrictCode=65000050"
URL_518 = "https://www.518.com.tw/job-index-P-{page}.html?ab=2035002021&aa=3001002007"
KIDEDU_LIST = "https://kidedu.ntpc.edu.tw/p/403-1000-9-{page}.php"


def get(url: str, tries: int = 3) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"})
    for n in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except OSError:
            if n == tries - 1:
                raise
            time.sleep(10)
    raise RuntimeError("unreachable")


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def is_jiaobao(title: str) -> bool:
    """職稱要有「教保員」，且不是只有「助理教保員」。"""
    t = title.replace("助理教保員", "")
    return "教保員" in t or "教保人員" in t


def roc_to_iso(s: str) -> str | None:
    m = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}" if m else None


def fetch_k12(today: str) -> list[dict]:
    page = get(K12_LIST)
    items = []
    for detail_path in dict.fromkeys(re.findall(r'data-vacurl="([^"]+)"', page)):
        url = K12_BASE + html.unescape(detail_path)
        d = html.unescape(get(url))

        def field(label: str) -> str:
            m = re.search(label + r"\s*[:：]?\s*</th>\s*<td[^>]*>(.*?)</td>", d, re.S)
            return text(m[1]) if m else ""

        def inline(label: str) -> str:
            m = re.search(label + r"[:：]\s*([^<]+)", d)
            return m[1].strip() if m else ""

        rows = re.findall(
            r'data-th="科目\(職缺\)">(.*?)</td>\s*<td data-th="缺額類科">(.*?)</td>.*?data-th="名額">(.*?)</td>',
            d, re.S,
        )
        positions = [(text(a), text(b), text(c)) for a, b, c in rows]
        jb = [p for p in positions if is_jiaobao(p[0])]
        if not jb:
            continue
        deadline = roc_to_iso(inline("報名截止日"))
        exam = roc_to_iso(inline("甄試日期"))
        last_day = deadline or exam
        if last_day and last_day < today:
            continue
        school = field("學校名稱")
        items.append({
            "source": "人才庫",
            "title": "、".join(f"{p[0]} {p[2]} 名" for p in jb),
            "org": school,
            "salary": "登入人才庫後查看",
            "place": field("學校地址"),
            "posted": roc_to_iso(field("刊登日期")),
            "deadline": deadline,
            "exam_date": exam,
            "period": inline("聘任期間"),
            "vacancy_type": field("職缺類型"),
            "tags": sorted({p[1] for p in jb if p[1]}),
            "url": url,
        })
    return items


def fetch_518() -> list[dict]:
    items = []
    for page in range(1, 6):
        h = get(URL_518.format(page=page))
        cards = re.findall(r'<div class="job__card[^"]*" data-id="(\w+)" data-url="([^"]+)">(.*?)<div class="job__actions">', h, re.S)
        if not cards:
            break
        for _id, url, body in cards:
            title = text(re.search(r'class="job__title[^"]*"[^>]*>(.*?)</a>', body, re.S)[1])
            org_m = re.search(r'job__comp__name">(.*?)</span>', body, re.S)
            sal_m = re.search(r'job__salary">(.*?)</p>', body, re.S)
            summ = [text(x) for x in re.findall(r"<li>(.*?)</li>", body, re.S)]
            salary = text(sal_m[1]) if sal_m else ""
            if not is_jiaobao(title) or "新莊" not in " ".join(summ) or "時薪" in salary:
                continue
            items.append({
                "source": "518",
                "title": title,
                "org": text(org_m[1]) if org_m else "",
                "salary": salary,
                "place": " / ".join(summ),
                "url": url,
                "tags": [],
            })
        if 'job-index-P-%d.html' % (page + 1) not in h:
            break
    return items


def fetch_kidedu() -> list[dict]:
    notices = []
    # 教保員甄選，以及升正式教師路上會用到的公告（幼教專班、教檢、教甄）
    pat = re.compile(r"(教保員.*(甄選|甄試|招募|徵才))|專班|師資職前|教師資格考試|教師甄選|教甄")
    for page in (1, 2, 3):
        h = get(KIDEDU_LIST.format(page=page))
        for url, title in re.findall(r'<a href="(https://kidedu\.ntpc\.edu\.tw/p/406-[^"]+)"[^>]*title="([^"]*)"', h):
            title = html.unescape(title).replace("(原頁面開啟)", "").strip()
            if pat.search(title) and not re.search(r"廚工|護理|成績查詢|試場|碩士", title):
                notices.append({"title": title, "url": url})
    return list({n["url"]: n for n in notices}.values())


def main() -> int:
    now = datetime.now(TW)
    today = now.strftime("%Y-%m-%d")
    old = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    first_seen = {i["url"]: i.get("first_seen", today) for i in old.get("items", [])}
    first_seen_n = {n["url"]: n.get("first_seen", today) for n in old.get("notices", [])}

    items, errors = [], []
    for name, fn in (("人才庫", lambda: fetch_k12(today)), ("518", fetch_518)):
        try:
            items += fn()
        except Exception as e:  # 單一來源失敗不影響其他來源
            errors.append(f"{name}: {e}")
            items += [i for i in old.get("items", []) if i["source"] == name]
    try:
        notices = fetch_kidedu()
    except Exception as e:
        errors.append(f"新北市幼教資源網: {e}")
        notices = old.get("notices", [])

    for i in items:
        i["first_seen"] = first_seen.get(i["url"], i.get("posted") or today)
    for n in notices:
        n["first_seen"] = first_seen_n.get(n["url"], today)
    items.sort(key=lambda i: (i.get("deadline") or "9999", i["first_seen"]), reverse=False)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated_at": now.strftime("%Y-%m-%d %H:%M"),
        "items": items,
        "notices": notices,
        "errors": errors,
    }, ensure_ascii=False, indent=1), "utf-8")
    print(f"{len(items)} items, {len(notices)} notices, errors={errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
