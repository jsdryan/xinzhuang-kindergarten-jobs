"""考試日程：每天更新 docs/exams.json。

- 新北市公幼契約進用教保員甄選、新北市國小暨幼兒園教師甄選：
  在新北市幼兒教育資源網找「新北市N學年度…簡章」公告，從公告內文的「（一）…：…年…月…日」抓日程。
- 教師資格考試（教檢）：教育部試務網站「重要日程」頁；尚未公告完整日程時，從「最新消息」抓「公告N年度…日期為M/D」。
- 該年度官方還沒公告的項目，用最近一次正式日期往後推一年，標記 est=true（網頁顯示「預估」）。
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TW = timezone(timedelta(hours=8))
OUT = Path(__file__).resolve().parent.parent / "docs" / "exams.json"
KIDEDU_LIST = "https://kidedu.ntpc.edu.tw/p/403-1000-9-{page}.php"
TQA = "https://tqa.rcpet.edu.tw/TEA_Exam/"

NTPC_EXAMS = {
    "kg_staff": re.compile(r"新北市(\d{3})學年度公立幼兒園契約進用教保員甄選簡章$"),
    "teacher_hire": re.compile(r"新北市(\d{3})學年度國民小學暨幼兒園教師甄選簡章$"),
}
CN_NUM = "一二三四五六七八九十"


def plain(h: str) -> str:
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()


def kind_of(label: str) -> str:
    if "簡章" in label:
        return "notice"
    if re.search(r"放榜|錄取|分發|選填|結果|成績", label):
        return "result"
    if re.search(r"報名|繳費", label):
        return "register"
    if re.search(r"試|考", label):
        return "exam"
    return "other"


def iso(roc_year: int, m: int, d: int) -> str:
    return date(roc_year + 1911, m, d).isoformat()


def parse_ntpc_post(body: str, roc_year: int, posted: str | None) -> list[dict]:
    """公告內文「（一）筆試時間：115年5月24日（星期日）」→ events。"""
    events = []
    if posted:
        events.append({"label": "簡章公告", "kind": "notice", "start": posted, "end": None})
    for seg in re.split(r"[（(][" + CN_NUM + r"]+[）)]", body)[1:]:
        label, _, rest = seg.partition("：")
        label = re.sub(r"\s+", "", label)[:12]
        if not rest or not label:
            continue
        rest = re.split(r"[二三四五六七八九]、", rest)[0]
        year = roc_year
        found = []
        for y, m, d in re.findall(r"(?:(\d{3})\s*(?:（以下同）)?\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日", rest):
            year = int(y) if y else year
            found.append(iso(year, int(m), int(d)))
        if found:
            events.append({"label": label, "kind": kind_of(label), "start": found[0],
                           "end": found[-1] if found[-1] != found[0] else None})
    return events


def fetch_ntpc(get, state: dict) -> None:
    """掃最新公告前幾頁，找到新年度簡章就存進 state；已知年度每天重抓內文（簡章修正日期會跟著更新）。"""
    for page in range(1, 6):
        h = get(KIDEDU_LIST.format(page=page))
        rows = re.findall(r'mdate[^>]*>\s*(\d{4}-\d{2}-\d{2})\s*</i>\s*<a href="([^"]+)"[^>]*title="([^"]*)"', h)
        for posted, url, title in rows:
            title = html.unescape(title).replace("(原頁面開啟)", "").strip()
            for key, pat in NTPC_EXAMS.items():
                m = pat.search(title)
                if m and m[1] not in state.setdefault(key, {}):
                    state[key][m[1]] = {"source": url, "posted": posted, "events": []}
    for key in NTPC_EXAMS:
        for year, rec in state.get(key, {}).items():
            if rec.get("source", "").startswith("https://kidedu"):
                body = plain(get(rec["source"]))
                hits = [i for i in (body.find("日程"), body.find("時程")) if i > 0]
                start = min(hits) if hits else 0
                events = parse_ntpc_post(body[start:] if start > 0 else body, int(year), rec.get("posted"))
                if len(events) > 1:
                    rec["events"] = events


def fetch_tqa(get, state: dict) -> None:
    rec = state.setdefault("qualify", {})
    # 重要日程頁（公告後才有表格）
    try:
        h = get(TQA + "TEA02.aspx")
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", h, flags=re.S)
        events, year = [], None
        for r in rows:
            cells = [plain(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=re.S)]
            line = " ".join(cells)
            dates = re.findall(r"(\d{3})\s*[年/.]\s*(\d{1,2})\s*[月/.]\s*(\d{1,2})", line)
            if not dates or not cells:
                continue
            year = year or int(dates[0][0])
            label = re.sub(r"\s+", "", cells[0])[:12] or "日程"
            ds = [iso(int(y), int(m), int(d)) for y, m, d in dates]
            events.append({"label": label, "kind": kind_of(label), "start": ds[0], "end": ds[-1] if ds[-1] != ds[0] else None})
        if events and year:
            # 重要日程表的年度：用考試日所在年
            exam_years = [int(e["start"][:4]) - 1911 for e in events if e["kind"] == "exam"]
            y = str(exam_years[0] if exam_years else year)
            rec[y] = {"source": TQA + "TEA02.aspx", "events": events}
    except Exception:
        pass
    # 最新消息：公告N年度…考試日期為M/D
    h = get(TQA)
    for y, m, d in re.findall(r"公告(\d{3})年度[^<]{0,40}?教師資格考試[^<]{0,10}?日期為\s*(\d{1,2})/(\d{1,2})", plain(h)):
        r = rec.setdefault(y, {"source": TQA, "events": []})
        if not any(e["kind"] == "exam" for e in r["events"]):
            r["events"].append({"label": "考試", "kind": "exam", "start": iso(int(y), int(m), int(d)), "end": None})


def shift_year(d: str | None) -> str | None:
    if not d:
        return None
    y, m, dd = map(int, d.split("-"))
    try:
        return date(y + 1, m, dd).isoformat()
    except ValueError:
        return date(y + 1, m, 28).isoformat()


def upcoming(state_exam: dict, today: str) -> dict:
    """挑還沒考完的最近一個年度；該年官方還沒公告的項目，用前一年的日期推一年補上（est=True）。"""
    years = sorted(state_exam, key=int)
    if not years:
        return {}
    last = lambda y: max((e.get("end") or e["start"] for e in state_exam[y]["events"]), default="0")
    target = next((y for y in years if last(y) >= today), str(int(years[-1]) + 1))
    prev = str(int(target) - 1)
    official = state_exam.get(target, {}).get("events", [])
    events = [dict(e, est=False) for e in official]
    if prev in state_exam:
        have = {e["kind"] for e in official}
        for e in state_exam[prev]["events"]:
            if e["kind"] not in have:
                events.append(dict(e, start=shift_year(e["start"]), end=shift_year(e.get("end")), est=True))
    events.sort(key=lambda e: e["start"])
    return {"year": int(target), "source": state_exam.get(target, {}).get("source") or state_exam.get(prev, {}).get("source"),
            "events": events}


def update(get, today: str) -> list[str]:
    errors = []
    old = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {}
    state = old.get("state", {})
    for name, fn in (("新北市甄選簡章", fetch_ntpc), ("教檢", fetch_tqa)):
        try:
            fn(get, state)
        except Exception as e:
            errors.append(f"{name}: {e}")
    OUT.write_text(json.dumps({
        "checked_at": datetime.now(TW).strftime("%Y-%m-%d %H:%M"),
        "upcoming": {k: upcoming(v, today) for k, v in state.items()},
        "state": state,
        "errors": errors,
    }, ensure_ascii=False, indent=1), "utf-8")
    return errors
