#!/usr/bin/env python3
"""Fetch USPTO Trademark Official Gazette weekly issues -> marks.jsonl + new_marks.jsonl.

KEYLESS data path (c72). The partner can never obtain an ODP API key
(ID.me), so the venture runs on the public gazette instead:
  list issues : GET  https://tm-eog-service.uspto.gov/eog-rest-service/api/external/search/publications
  issue XML   : GET  https://cdn.uspto.gov/doc/TMOGIssue_YYYYMMDD_entire?extension=xml
                (302 -> storage.googleapis.com, ~230MB, ST.96 XML)
Both verified live 2026-09-01 with plain curl, no auth. One issue per week
(Tuesdays); we pull at most a few per run and are polite (sequential, one
connection, downloads deleted after parsing).

Modes:
  --probe      list issues + show which are new. No writes.
  (default)    download unseen issues (first run: newest BACKFILL_ISSUES only)
               -> parse (tmog_parse) -> merge into marks.jsonl (dedupe by
               serial+event, keep newest pub_date; drop pub_date older than
               MAX_AGE_DAYS vs newest) -> write new_marks.jsonl (records not
               previously seen) for watch_run.py.
  --selftest   merge/window/new-record logic on fixtures. No network.

State files (product dir): fetched_issues.json {YYYY-MM-DD: true}
                           seen_keys.json      ["serial:event", ...]
Stdlib only.
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tmog_parse  # noqa: E402

LIST_URL = ("https://tm-eog-service.uspto.gov/eog-rest-service/api"
            "/external/search/publications")
ISSUE_URL = "https://cdn.uspto.gov/doc/TMOGIssue_%s_entire?extension=xml"
MARKS = os.path.join(HERE, "marks.jsonl")
NEW_MARKS = os.path.join(HERE, "new_marks.jsonl")
FETCHED = os.path.join(HERE, "fetched_issues.json")
SEEN = os.path.join(HERE, "seen_keys.json")
LAST_RESP = os.path.join(HERE, "tmog_last_response.json")
DL_DIR = os.path.join(HERE, "downloads")
MAX_AGE_DAYS = 120       # index window (~17 weekly issues)
BACKFILL_ISSUES = 4      # first-ever run: newest N issues (~1 month, ~1GB)
MAX_ISSUES_PER_RUN = 3   # steady state: 1/week; leaves room to catch up
UA = "tm-watch/1.0 (+https://github.com/APVentureEngine/trademark-watch)"


def _load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _read_jsonl(path):
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


def _write_jsonl(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    os.replace(tmp, path)


def list_issues():
    """-> sorted list of 'YYYY-MM-DD' issue dates with status PUBLI/final."""
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    with open(LAST_RESP, "w") as f:
        json.dump(data, f)
    out = []
    for e in data if isinstance(data, list) else []:
        d = e.get("publicationDate")
        if d and e.get("publicationStatusCode") == "PUBLI" and e.get("isFinalExtract", True):
            out.append(d)
    return sorted(set(out))


def download_issue(day, dest):
    url = ISSUE_URL % day.replace("-", "")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as r, open(dest, "wb") as f:
        n = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            n += len(chunk)
    return n


def key(r):
    return "%d:%s" % (r["serial"], r.get("event", ""))


def merge(existing, incoming, seen_keys):
    """Pure (selftested). Returns (rows, new_rows, seen).
    - dedupe by serial+event; newer pub_date wins
    - window: drop pub_date older than MAX_AGE_DAYS before newest pub_date
    - new_rows: incoming whose key not previously seen
    """
    by_key = {key(r): r for r in existing}
    seen = set(seen_keys)
    new_rows = []
    for r in incoming:
        k = key(r)
        old = by_key.get(k)
        if old is None or r["pub_date"] >= old["pub_date"]:
            by_key[k] = r
        if k not in seen:
            seen.add(k)
            new_rows.append(r)
    rows = sorted(by_key.values(), key=lambda r: (r["serial"], r.get("event", "")))
    if rows:
        newest = max(r["pub_date"] for r in rows)
        y, m, d = map(int, newest.split("-"))
        cutoff = (date(y, m, d) - timedelta(days=MAX_AGE_DAYS)).isoformat()
        rows = [r for r in rows if r["pub_date"] >= cutoff]
    # keep seen bounded to keys still inside the window + this run's new ones
    live = {key(r) for r in rows} | {key(r) for r in new_rows}
    return rows, new_rows, sorted(k for k in seen if k in live)


def floor_date(newest):
    y, m, d = map(int, newest.split("-"))
    return (date(y, m, d) - timedelta(days=MAX_AGE_DAYS)).isoformat()


def probe():
    issues = list_issues()
    fetched = _load(FETCHED, {})
    print("issues listed: %d (newest %s)" % (len(issues), issues[-1] if issues else "none"))
    print("unfetched (in window, newest 6): %s"
          % [d for d in issues if d not in fetched and d >= floor_date(issues[-1])][-6:])
    return 0


def run():
    issues = list_issues()
    if not issues:
        print("fetch_tmog: 0 issues listed — see tmog_last_response.json", file=sys.stderr)
        return 1
    fetched = _load(FETCHED, {})
    # only issues inside the rolling window are ever candidates — never crawl
    # the 13-year archive (682 issues) three at a time forever.
    floor = floor_date(issues[-1])
    todo = [d for d in issues if d not in fetched and d >= floor]
    limit = BACKFILL_ISSUES if not fetched else MAX_ISSUES_PER_RUN
    if len(todo) > limit:
        print("fetch_tmog: %d unfetched issues, taking newest %d" % (len(todo), limit))
        todo = todo[-limit:]
    if not todo:
        print("fetch_tmog: no new issues (newest listed %s)" % issues[-1])
        return 0
    os.makedirs(DL_DIR, exist_ok=True)
    incoming = []
    for day in todo:
        dest = os.path.join(DL_DIR, "TMOGIssue_%s.xml" % day)
        print("fetch_tmog: downloading issue %s" % day)
        n = download_issue(day, dest)
        stats = {}
        recs = list(tmog_parse.parse_file(dest, stats))
        os.remove(dest)
        print("fetch_tmog: %s -> %d MB, %s" % (day, n >> 20, json.dumps(stats, sort_keys=True)))
        if not recs:
            print("fetch_tmog: issue %s parsed to 0 records — schema drift? aborting"
                  % day, file=sys.stderr)
            return 1
        incoming.extend(recs)
        fetched[day] = True
    marks, new_rows, seen = merge(_read_jsonl(MARKS), incoming, _load(SEEN, []))
    _write_jsonl(MARKS, marks)
    _write_jsonl(NEW_MARKS, new_rows)
    with open(FETCHED, "w") as f:
        json.dump(fetched, f, indent=0, sort_keys=True)
    with open(SEEN, "w") as f:
        json.dump(seen, f)
    print("fetch_tmog: store=%d marks (%dd window), new-this-run=%d"
          % (len(marks), MAX_AGE_DAYS, len(new_rows)))
    return 0


def selftest():
    existing = [
        {"serial": 1, "mark": "OLD", "filing_date": "2025-11-01", "pub_date": "2026-01-06",
         "event": "published", "classes": [9]},
        {"serial": 2, "mark": "KEEP", "filing_date": "2026-02-01", "pub_date": "2026-08-25",
         "event": "published", "classes": [25]},
    ]
    incoming = [
        {"serial": 2, "mark": "KEEP", "filing_date": "2026-02-01", "pub_date": "2026-09-01",
         "event": "registered", "classes": [25]},   # same serial, new event -> new
        {"serial": 3, "mark": "NEW", "filing_date": "2026-03-01", "pub_date": "2026-09-01",
         "event": "published", "classes": [42]},
        {"serial": 2, "mark": "KEEP", "filing_date": "2026-02-01", "pub_date": "2026-08-25",
         "event": "published", "classes": [25]},    # re-parsed duplicate -> not new
    ]
    rows, new_rows, seen = merge(existing, incoming, ["1:published", "2:published"])
    assert [key(r) for r in rows] == ["2:published", "2:registered", "3:published"], rows
    assert [key(r) for r in new_rows] == ["2:registered", "3:published"], new_rows
    assert "1:published" not in seen and "3:published" in seen, seen
    print("fetch_tmog selftest OK")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--selftest":
        selftest()
    elif a and a[0] == "--probe":
        sys.exit(probe())
    else:
        sys.exit(run())
