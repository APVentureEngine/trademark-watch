#!/usr/bin/env python3
"""Fetch USPTO ODP TRTDXFAP daily files -> marks.jsonl + new_marks.jsonl.

Written BEFORE the key exists (A010 pending) against the documented ODP API
surface; every real-API assumption is isolated in _list_files/_download and
fails LOUDLY with the raw payload dumped to odp_last_response.json so the
first key-in-hand run is a 2-minute reconcile, not a rebuild.

Modes:
  --probe            key sanity: GET product metadata, print HTTP status,
                     rate-limit-ish headers, discovered file entries. No writes.
  (default)          list files -> download ones not in fetched_files.json ->
                     parse (tdxf_parse) -> merge into marks.jsonl (dedupe by
                     serial, keep latest transaction; drop filing_date older
                     than MAX_AGE_DAYS vs newest) -> write new_marks.jsonl
                     (records whose serial was not previously seen) for
                     watch_run.py.
  --selftest         exercises merge/window/new-serial logic on fixtures. No
                     network, no key.

State files (product dir): fetched_files.json  {filename: iso-date-ingested}
                           seen_serials.json   [serial,...]
Env: USPTO_ODP_API_KEY (required for network modes).
Stdlib only.
"""
import json
import os
import ssl
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tdxf_parse  # noqa: E402

API_BASE = "https://api.uspto.gov/api/v1/datasets/products/TRTDXFAP"
MARKS = os.path.join(HERE, "marks.jsonl")
NEW_MARKS = os.path.join(HERE, "new_marks.jsonl")
FETCHED = os.path.join(HERE, "fetched_files.json")
SEEN = os.path.join(HERE, "seen_serials.json")
LAST_RESP = os.path.join(HERE, "odp_last_response.json")
DL_DIR = os.path.join(HERE, "downloads")
MAX_AGE_DAYS = 120  # keep marks.jsonl bounded; index window is 90d


def _key():
    k = os.environ.get("USPTO_ODP_API_KEY", "").strip()
    if not k:
        print("fetch: USPTO_ODP_API_KEY not set (A010). Nothing fetched.",
              file=sys.stderr)
        sys.exit(2)
    return k


def _get(url, key, binary=False):
    req = urllib.request.Request(url, headers={
        "X-API-KEY": key, "Accept": "*/*",
        "User-Agent": "tm-watch/1.0 (contact via github.com/APProj/trademark-watch)"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
        data = r.read()
        return r.status, dict(r.headers), data if binary else data.decode("utf-8", "replace")


def _walk_file_entries(obj, out):
    """Defensively find dicts that look like file entries anywhere in the JSON:
    need a name-ish key and a download-url-ish key."""
    if isinstance(obj, dict):
        name = url = size = fdate = None
        for k, v in obj.items():
            lk = k.lower()
            if isinstance(v, str):
                if "filename" in lk or lk == "name" or "filetitle" in lk:
                    name = name or v
                if "download" in lk and ("uri" in lk or "url" in lk):
                    url = url or v
                if "filedate" in lk or "fromdate" in lk:
                    fdate = fdate or v
            if isinstance(v, (int, float)) and "size" in lk:
                size = v
        if name and url:
            out.append({"name": name, "url": url, "size": size, "date": fdate})
        for v in obj.values():
            _walk_file_entries(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_file_entries(v, out)


def list_files(key):
    url = API_BASE + "?includeFiles=true"
    status, headers, body = _get(url, key)
    try:
        payload = json.loads(body)
    except ValueError:
        payload = {"_raw_non_json": body[:2000]}
    with open(LAST_RESP, "w") as f:
        json.dump(payload, f, indent=1)
    entries = []
    _walk_file_entries(payload, entries)
    # dedupe by name, newest-name-last (TDXF names embed dates: apc<YYMMDD>.zip)
    uniq = {}
    for e in entries:
        uniq[e["name"]] = e
    return status, headers, sorted(uniq.values(), key=lambda e: e["name"])


def probe():
    key = _key()
    status, headers, files = list_files(key)
    print("probe: HTTP %s from %s" % (status, API_BASE))
    for h in sorted(headers):
        if any(t in h.lower() for t in ("rate", "limit", "quota", "retry")):
            print("probe: header %s: %s" % (h, headers[h]))
    print("probe: %d file entries discovered (raw JSON -> odp_last_response.json)"
          % len(files))
    for e in files[-10:]:
        print("probe:   %s  size=%s date=%s" % (e["name"], e["size"], e["date"]))
    if not files:
        print("PROBE-WARNING: 0 file entries — response shape differs from "
              "expectation; read odp_last_response.json and adapt "
              "_walk_file_entries.", file=sys.stderr)
        return 1
    return 0


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
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def _write_jsonl(path, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    os.replace(tmp, path)


def merge(existing, incoming, seen_serials):
    """Pure merge logic (selftested): returns (marks_rows, new_rows, seen).
    - dedupe by serial; incoming wins if newer transaction_date (or always,
      when no transaction dates present)
    - window: drop filing_date older than MAX_AGE_DAYS before the newest
      filing_date across the merged set
    - new_rows = incoming records whose serial not in seen_serials
    """
    from datetime import date, timedelta
    by_serial = {r["serial"]: r for r in existing}
    new_rows = []
    seen = set(seen_serials)
    for r in incoming:
        old = by_serial.get(r["serial"])
        if old is None or r.get("transaction_date", "9999") >= old.get("transaction_date", ""):
            by_serial[r["serial"]] = r
        if r["serial"] not in seen:
            seen.add(r["serial"])
            new_rows.append(r)
    rows = sorted(by_serial.values(), key=lambda r: r["serial"])
    if rows:
        newest = max(r["filing_date"] for r in rows)
        y, m, d = map(int, newest.split("-"))
        cutoff = (date(y, m, d) - timedelta(days=MAX_AGE_DAYS)).isoformat()
        rows = [r for r in rows if r["filing_date"] >= cutoff]
    return rows, new_rows, sorted(seen)


def run():
    key = _key()
    status, _headers, files = list_files(key)
    if not files:
        print("fetch: HTTP %s but 0 file entries — see odp_last_response.json"
              % status, file=sys.stderr)
        sys.exit(1)
    fetched = _load(FETCHED, {})
    todo = [e for e in files if e["name"] not in fetched]
    # first-ever run: take only the newest 7 files (backfill window), not years
    if not fetched and len(todo) > 7:
        print("fetch: first run, limiting backfill to newest 7 of %d files" % len(todo))
        todo = todo[-7:]
    if not todo:
        print("fetch: no new files (of %d listed)" % len(files))
        return 0
    os.makedirs(DL_DIR, exist_ok=True)
    incoming = []
    for e in todo:
        dest = os.path.join(DL_DIR, os.path.basename(e["name"]))
        print("fetch: downloading %s" % e["name"])
        _st, _h, data = _get(e["url"], key, binary=True)
        with open(dest, "wb") as f:
            f.write(data)
        n_before = len(incoming)
        incoming.extend(tdxf_parse.parse_file(dest))
        print("fetch: %s -> %d records" % (e["name"], len(incoming) - n_before))
        fetched[e["name"]] = True
        os.remove(dest)  # keep disk clean; marks.jsonl is the store
    marks, new_rows, seen = merge(_read_jsonl(MARKS), incoming, _load(SEEN, []))
    _write_jsonl(MARKS, marks)
    _write_jsonl(NEW_MARKS, new_rows)
    with open(FETCHED, "w") as f:
        json.dump(fetched, f, indent=0, sort_keys=True)
    with open(SEEN, "w") as f:
        json.dump(seen, f)
    print("fetch: store=%d marks (%dd window), new-this-run=%d serials"
          % (len(marks), MAX_AGE_DAYS, len(new_rows)))
    return 0


def selftest():
    existing = [
        {"serial": 1, "mark": "OLD MARK", "filing_date": "2026-01-01", "classes": [9],
         "transaction_date": "2026-01-02"},
        {"serial": 2, "mark": "KEEP ME", "filing_date": "2026-08-01", "classes": [25],
         "transaction_date": "2026-08-02"},
    ]
    incoming = [
        {"serial": 2, "mark": "KEEP ME AMENDED", "filing_date": "2026-08-01",
         "classes": [25], "transaction_date": "2026-08-30"},   # update, not new
        {"serial": 3, "mark": "BRAND NEW", "filing_date": "2026-08-29",
         "classes": [42], "transaction_date": "2026-08-30"},   # new serial
    ]
    rows, new_rows, seen = merge(existing, incoming, [1, 2])
    assert [r["serial"] for r in rows] == [2, 3], rows          # serial 1 aged out
    assert rows[0]["mark"] == "KEEP ME AMENDED", rows[0]        # newer tx wins
    assert [r["serial"] for r in new_rows] == [3], new_rows     # only 3 is new
    assert seen == [1, 2, 3], seen
    # stale incoming must NOT clobber newer stored record
    rows2, _n2, _s2 = merge(rows, [{"serial": 3, "mark": "STALE", "filing_date":
                            "2026-08-29", "classes": [], "transaction_date":
                            "2026-08-01"}], seen)
    assert dict((r["serial"], r["mark"]) for r in rows2)[3] == "BRAND NEW"
    print("fetch selftest: PASS (merge/window/new-serial/stale-guard)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--probe" in sys.argv:
        sys.exit(probe())
    sys.exit(run())
