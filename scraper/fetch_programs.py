"""幼教專班（幼兒園在職人員修習幼兒園教師師資職前教育課程專班）：每天更新 docs/programs.json。

- 各校：抓學校的幼教專班公告頁，找標題含「N學年度…幼教專班／幼兒園在職人員修習」的最新年度公告。
- 全國時程：教育部每年核定開班並統一報名期間，新北市幼兒教育資源網會轉知；
  在轉知公告內文找「簡章…於N年M月D日」「N年M月D日至N年M月D日開放第X階段報名」。
  還沒轉知的年度沿用最近一次正式時程往後推一年，標記 est=true。
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TW = timezone(timedelta(hours=8))
OUT = Path(__file__).resolve().parent.parent / "docs" / "programs.json"
KIDEDU_LIST = "https://kidedu.ntpc.edu.tw/p/403-1000-9-{page}.php"
PAT = re.compile(r"幼教專班|幼兒園在職人員修習")

# 已確認有開幼教專班的學校（115 學年度）。新增學校只要加一行。
SCHOOLS = [
    {"name": "國立臺北教育大學", "area": "北部", "url": "https://dicentue.ntue.edu.tw/p/403-1012-955-1.php?Lang=zh-tw"},
    {"name": "臺北市立大學", "area": "北部", "url": "https://cte.utaipei.edu.tw/p/412-1013-9618.php?Lang=zh-tw"},
    {"name": "國立臺灣師範大學", "area": "北部", "url": "https://tecs.otecs.ntnu.edu.tw/", "note": "教育部公文列名開班；公告頁待確認"},
    {"name": "國立清華大學", "area": "新竹", "url": "https://ndcee.site.nthu.edu.tw/p/404-1109-306929.php", "note": "週六上課，南大校區"},
    {"name": "國立東華大學", "area": "宜蘭／花蓮", "url": "https://littletree.ndhu.edu.tw/p/426-1023-20.php?Lang=zh-tw"},
    {"name": "朝陽科技大學", "area": "臺中", "url": "https://edu.cyut.edu.tw/"},
    {"name": "台南應用科技大學", "area": "臺南", "url": "https://edcourse.tut.edu.tw/p/406-1024-4894,r101.php?Lang=zh-tw"},
    {"name": "國立屏東大學", "area": "高雄（假日班）", "url": "https://ec.nptu.edu.tw/p/412-1119-6275.php?Lang=zh-tw"},
]


def plain(h: str) -> str:
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def iso(roc: str, m: str, d: str) -> str:
    return date(int(roc) + 1911, int(m), int(d)).isoformat()


def fetch_school(get, s: dict) -> dict:
    h = get(s["url"])
    items = []
    for href, t in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h, re.S):
        t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", t))).strip()
        y = re.search(r"(\d{3})學年度", t)
        if PAT.search(t) and y and not re.search(r"\.(pdf|docx?|odt)$", t, re.I):
            url = html.unescape(href)
            if url.startswith("/"):
                url = re.match(r"https?://[^/]+", s["url"])[0] + url
            items.append({"year": int(y[1]), "title": t, "url": url})
    body_years = [int(y) for y in re.findall(r"(\d{3})\s*學年度\s*(?:幼教專班|幼兒園在職人員修習)", plain(h))]
    latest = max([i["year"] for i in items] + body_years, default=None)
    seen, latest_items = set(), []
    for i in items:
        if i["year"] == latest and i["title"] not in seen:
            seen.add(i["title"])
            latest_items.append({"title": i["title"], "url": i["url"]})
    return {"latest_year": latest, "items": latest_items[:4]}


def parse_national(body: str) -> list[dict]:
    events = []
    m = re.search(r"簡章[^。]{0,20}?於\s*(\d{3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", body)
    if m:
        events.append({"label": "各校簡章公告", "kind": "notice", "start": iso(*m.groups()), "end": None})
    for y1, m1, d1, y2, m2, d2, stage in re.findall(
            r"(\d{3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*至\s*(\d{3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*開放(第.階段報名)", body):
        events.append({"label": stage, "kind": "register", "start": iso(y1, m1, d1), "end": iso(y2, m2, d2)})
    return events


def shift_year(d):
    if not d:
        return None
    y, m, dd = map(int, d.split("-"))
    return date(y + 1, m, min(dd, 28) if (m, dd) == (2, 29) else dd).isoformat()


def update(get, today: str) -> list[str]:
    errors = []
    old = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    national = old.get("national", {})
    old_schools = {s["name"]: s for s in old.get("schools", [])}

    # 全國時程：新北市幼教網轉知
    try:
        for page in range(1, 6):
            h = get(KIDEDU_LIST.format(page=page))
            for posted, url, title in re.findall(r'mdate[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</i>\s*<a href="([^"]+)"[^>]*title="([^"]*)"', h):
                title = html.unescape(title)
                y = re.search(r"(\d{3})學年度", title)
                if y and PAT.search(title) and re.search(r"報考|報名|招生", title) and y[1] not in national:
                    ev = parse_national(plain(get(url)))
                    if ev:
                        national[y[1]] = {"source": url, "events": ev}
    except Exception as e:
        errors.append(f"幼教專班全國時程: {e}")

    schools = []
    for s in SCHOOLS:
        try:
            r = fetch_school(get, s)
        except Exception as e:
            errors.append(f"幼教專班 {s['name']}: {e}")
            r = {k: old_schools.get(s["name"], {}).get(k) for k in ("latest_year", "items")}
        schools.append({**s, **r})

    # 還沒考完的最近年度；未公告就用前一年推一年
    years = sorted(national, key=int)
    last = lambda y: max((e.get("end") or e["start"] for e in national[y]["events"]), default="0")
    target = next((y for y in years if last(y) >= today), str(int(years[-1]) + 1) if years else None)
    upcoming = {}
    if target:
        if target in national:
            upcoming = {"year": int(target), "source": national[target]["source"],
                        "events": [dict(e, est=False) for e in national[target]["events"]]}
        elif str(int(target) - 1) in national:
            prev = national[str(int(target) - 1)]
            upcoming = {"year": int(target), "source": prev["source"],
                        "events": [dict(e, start=shift_year(e["start"]), end=shift_year(e.get("end")), est=True) for e in prev["events"]]}

    OUT.write_text(json.dumps({
        "checked_at": datetime.now(TW).strftime("%Y-%m-%d %H:%M"),
        "upcoming": upcoming,
        "national": national,
        "schools": schools,
        "errors": errors,
    }, ensure_ascii=False, indent=1), "utf-8")
    return errors
