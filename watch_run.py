#!/usr/bin/env python3
"""Daily watch runner: watchlist.json vs new_marks.jsonl -> alert files.

For every ACTIVE watch (not past `expires`), compare the watched mark against
every NEW filing (new_marks.jsonl from fetch_trtdxfap.py) with matcher.compare
— against the filing's mark text AND its pseudo-mark variants. Hits become one
markdown alert file per watch per day in the PRIVATE alerts repo
(APProj/tm-watch-alerts), which subscribers watch — GitHub sends the email
(proven warn-feed pattern; zero recurring human steps).

Modes:
  (default)     needs new_marks.jsonl + watchlist.json; writes alert files
                into alerts_repo/ clone (clones if absent, real data only),
                commits+pushes when there are changes. No new filings -> no
                files, exit 0 (quiet day is a valid day).
  --dry         compute + print hits, write nothing, push nothing.
  --selftest    planted watchlist vs planted filings in a temp dir; asserts
                hit + non-hit + expiry handling. No network, no git.

Honesty rails: alerts state filing serial + date + reasons and link TSDR;
wording is "similar filing detected — review", never a legal conclusion.
Stdlib only.
"""
import json
import os
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import matcher  # noqa: E402

WATCHLIST = os.path.join(HERE, "watchlist.json")
NEW_MARKS = os.path.join(HERE, "new_marks.jsonl")
ALERTS_DIR = os.path.join(HERE, "alerts_repo")
OWNER, REPO = "APProj", "tm-watch-alerts"

DISCLAIMER = ("_Automated similarity flags for human review. Not legal advice; "
              "no opinion on likelihood of confusion. Verify at the TSDR link._")


def tsdr(serial):
    return ("https://tsdr.uspto.gov/#caseNumber=%d&caseType=SERIAL_NO"
            "&searchType=statusSearch" % serial)


def hits_for(watch_mark, filings):
    """[(filing, reasons)] for one watched mark. Pseudo-marks count too."""
    out = []
    for f in filings:
        flag, reasons, _d = matcher.compare(watch_mark, f["mark"])
        if not flag:
            for pm in f.get("pseudo", []):
                pflag, preasons, _d2 = matcher.compare(watch_mark, pm)
                if pflag:
                    flag, reasons = True, ["pseudo-mark:" + r for r in preasons]
                    break
        if flag:
            out.append((f, reasons))
    return out


def render_alert(watch_mark, day, hits):
    lines = ["# TM Watch alert — %s — %s" % (watch_mark, day), "",
             "%d new USPTO filing(s) similar to your watched mark." % len(hits),
             "", "| Serial | Mark | Filed | Classes | Why flagged | Status link |",
             "|---|---|---|---|---|---|"]
    for f, reasons in sorted(hits, key=lambda h: h[0]["serial"]):
        lines.append("| %d | %s | %s | %s | %s | [TSDR](%s) |" % (
            f["serial"], f["mark"].replace("|", "\\|"), f["filing_date"],
            " ".join(str(c) for c in f.get("classes", [])) or "—",
            ", ".join(reasons).replace("|", "\\|"), tsdr(f["serial"])))
    lines += ["", DISCLAIMER, ""]
    return "\n".join(lines)


def run(watchlist, filings, today, out_dir=None, write=True):
    """Pure core. Returns list of (sale_id, user, watch_mark, n_hits, path)."""
    results = []
    for sid, w in sorted(watchlist.items()):
        if w.get("expires") and w["expires"] < today:
            continue
        hits = hits_for(w["mark"], filings)
        if not hits:
            continue
        path = None
        if write and out_dir:
            safe_user = "".join(c for c in w.get("user", "unknown")
                                if c.isalnum() or c in "-_") or "unknown"
            d = os.path.join(out_dir, "alerts", safe_user)
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, "%s.md" % today)
            with open(path, "w") as f:
                f.write(render_alert(w["mark"], today, hits))
        results.append((sid, w.get("user"), w["mark"], len(hits), path))
    return results


def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True,
                          text=True)


def real_run(dry=False):
    if not os.path.exists(NEW_MARKS):
        print("watch_run: no new_marks.jsonl (run fetch first) — nothing to do")
        return 0
    watchlist = {}
    if os.path.exists(WATCHLIST):
        with open(WATCHLIST) as f:
            watchlist = json.load(f)
    if not watchlist:
        print("watch_run: watchlist empty — 0 watches, done")
        return 0
    filings = []
    with open(NEW_MARKS) as f:
        for line in f:
            if line.strip():
                filings.append(json.loads(line))
    today = date.today().isoformat()
    if dry:
        for sid, user, mark, n, _p in run(watchlist, filings, today, write=False):
            print("watch_run DRY: %s (%s) %r -> %d hit(s)" % (sid, user, mark, n))
        return 0
    tok = os.environ.get("GITHUB_TOKEN", "")
    if not os.path.isdir(os.path.join(ALERTS_DIR, ".git")):
        if not tok:
            print("watch_run: GITHUB_TOKEN missing, cannot clone alerts repo",
                  file=sys.stderr)
            return 1
        r = _git(["clone", "https://x-access-token:%s@github.com/%s/%s.git"
                  % (tok, OWNER, REPO), ALERTS_DIR], HERE)
        if r.returncode != 0:
            print("watch_run: clone failed: %s" % r.stderr.strip()[-400:],
                  file=sys.stderr)
            return 1
    results = run(watchlist, filings, today, out_dir=ALERTS_DIR)
    total = sum(n for _s, _u, _m, n, _p in results)
    for sid, user, mark, n, path in results:
        print("watch_run: %s (%s) %r -> %d hit(s) -> %s" % (sid, user, mark, n, path))
    if results:
        _git(["add", "-A"], ALERTS_DIR)
        if _git(["diff", "--cached", "--quiet"], ALERTS_DIR).returncode != 0:
            _git(["commit", "-m", "alerts %s" % today], ALERTS_DIR)
            r = _git(["push", "https://x-access-token:%s@github.com/%s/%s.git"
                      % (tok, OWNER, REPO), "HEAD"], ALERTS_DIR)
            if r.returncode != 0:
                print("watch_run: PUSH FAILED: %s" % r.stderr.strip()[-400:],
                      file=sys.stderr)
                return 1
    print("watch_run: %d watch(es) checked vs %d new filings, %d alert file(s), %d total hit(s)"
          % (len(watchlist), len(filings), len(results), total))
    return 0


def selftest():
    import tempfile
    watchlist = {
        "s1": {"mark": "NIKE", "user": "alice", "start": "2026-09-01",
               "expires": "2027-09-01"},
        "s2": {"mark": "QUARTZLY", "user": "bob", "start": "2026-09-01",
               "expires": "2027-09-01"},
        "s3": {"mark": "NIKE", "user": "eve", "start": "2025-01-01",
               "expires": "2026-01-01"},  # expired — must be skipped
    }
    filings = [
        {"serial": 90000001, "mark": "NYKE ATHLETICS", "filing_date": "2026-08-30",
         "classes": [25]},
        {"serial": 90000002, "mark": "TOTALLY UNRELATED COFFEE",
         "filing_date": "2026-08-30", "classes": [30],
         "pseudo": ["NIKEY"]},                      # hits only via pseudo
        {"serial": 90000003, "mark": "BLUE RIVER CONSULTING",
         "filing_date": "2026-08-30", "classes": [35]},
    ]
    with tempfile.TemporaryDirectory() as td:
        res = run(watchlist, filings, "2026-09-01", out_dir=td)
        got = {(sid, n) for sid, _u, _m, n, _p in res}
        assert got == {("s1", 2)}, res  # alice: NYKE + pseudo NIKEY; bob 0; eve expired
        path = res[0][4]
        body = open(path).read()
        assert "NYKE ATHLETICS" in body and "pseudo-mark:" in body, body
        assert "90000003" not in body, body
        assert "Not legal advice" in body
        assert "tsdr.uspto.gov" in body
    # empty filings day
    assert run(watchlist, [], "2026-09-01", write=False) == []
    print("watch_run selftest: PASS (hit, pseudo-hit, non-hit, expiry, empty-day)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(real_run(dry="--dry" in sys.argv))
