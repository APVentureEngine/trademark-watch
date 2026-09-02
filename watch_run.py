#!/usr/bin/env python3
"""Daily watch runner: watchlist.json vs new_marks.jsonl -> alert files.

For every ACTIVE watch (not past `expires`), compare the watched mark against
every NEW filing (new_marks.jsonl from fetch_trtdxfap.py) with matcher.compare
— against the filing's mark text AND its pseudo-mark variants. Hits become one
markdown alert file per watch per day in the PRIVATE alerts repo
(APVentureEngine/tm-watch-alerts) AND — since c73 — one EMAIL per watch per day to
the purchaser's address via mailer.py (Brevo), idempotent through
alerts_sent.json. Email is the primary channel (SMB buyers have no GitHub);
the repo is history/RSS for technical users. If the mailer is not configured
the emails are skipped LOUDLY (counted in stdout) and the repo path still runs.

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
import mailer   # noqa: E402

WATCHLIST = os.path.join(HERE, "watchlist.json")
NEW_MARKS = os.path.join(HERE, "new_marks.jsonl")
ALERTS_DIR = os.path.join(HERE, "alerts_repo")
OWNER, REPO = "APVentureEngine", "tm-watch-alerts"
SENT = os.path.join(HERE, "alerts_sent.json")
BUY_URL = "https://approj.gumroad.com/l/pwvfma"

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
             "%d mark(s) in the latest USPTO Official Gazette similar to your "
             "watched mark. A mark *published for opposition* can be opposed "
             "(or an extension requested) for 30 days from its Gazette date." % len(hits),
             "", "| Serial | Mark | Gazette date | Event | Classes | Why flagged | Status link |",
             "|---|---|---|---|---|---|---|"]
    for f, reasons in sorted(hits, key=lambda h: h[0]["serial"]):
        lines.append("| %d | %s | %s | %s | %s | %s | [TSDR](%s) |" % (
            f["serial"], f["mark"].replace("|", "\\|"),
            f.get("pub_date") or f["filing_date"],
            {"published": "Published for opposition", "registered": "Registered"}.get(f.get("event"), "Filed"),
            " ".join(str(c) for c in f.get("classes", [])) or "—",
            ", ".join(reasons).replace("|", "\\|"), tsdr(f["serial"])))
    lines += ["", DISCLAIMER, ""]
    return "\n".join(lines)


def _h(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_alert_html(watch_mark, day, hits):
    rows = []
    for f, reasons in sorted(hits, key=lambda h: h[0]["serial"]):
        rows.append("<tr><td>%d</td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td>"
                    "<td>%s</td><td><a href=\"%s\">TSDR</a></td></tr>" % (
                        f["serial"], _h(f["mark"]), _h(f.get("pub_date") or f["filing_date"]),
                        {"published": "Published for opposition", "registered": "Registered"}.get(f.get("event"), "Filed"),
                        _h(" ".join(str(c) for c in f.get("classes", [])) or "—"),
                        _h(", ".join(reasons)), tsdr(f["serial"])))
    return ("<h2>TM Watch alert — %s — %s</h2>"
            "<p>%d mark(s) in the latest USPTO Official Gazette similar to your watched mark "
            "<b>%s</b>. A mark <i>published for opposition</i> can be opposed (or an extension "
            "requested) for 30 days from its Gazette date.</p>"
            "<table border=\"1\" cellpadding=\"6\" style=\"border-collapse:collapse;font-size:14px\">"
            "<tr><th>Serial</th><th>Mark</th><th>Gazette date</th><th>Event</th><th>Classes</th>"
            "<th>Why flagged</th><th>Status</th></tr>%s</table>"
            % (_h(watch_mark), day, len(hits), _h(watch_mark), "".join(rows)))


def dispatch_emails(watchlist, results, today, sent, send_fn, hits_by_sid):
    """Pure-ish: decides which emails to send today and calls send_fn(to, subj,
    text, html) -> (ok, info). `sent` is mutated ({key: ts}). Returns a list of
    (key, ok, info). Keys: '<sid>:<day>' alerts, '<sid>:expiry' reminder."""
    out = []
    for sid, _user, mark, n, _path in results:
        w = watchlist.get(sid, {})
        email = w.get("email")
        key = "%s:%s" % (sid, today)
        if not email or key in sent:
            continue
        hits = hits_by_sid[sid]
        subj = "TM Watch: %d similar mark%s to %s in this week's Gazette" % (n, "" if n == 1 else "s", mark)
        ok, info = send_fn(email, subj, render_alert(mark, today, hits), render_alert_html(mark, today, hits))
        if ok:
            sent[key] = today
        out.append((key, ok, info))
    for sid, w in sorted(watchlist.items()):
        email, exp = w.get("email"), w.get("expires")
        key = "%s:expiry" % sid
        if not email or not exp or key in sent:
            continue
        try:
            ey, em, ed = map(int, exp.split("-"))
            ty, tm, td = map(int, today.split("-"))
            left = (date(ey, em, ed) - date(ty, tm, td)).days
        except ValueError:
            continue
        if 0 <= left <= 14:
            text = ("Your TM Watch for %s expires on %s.\n\nRenew for another year at %s "
                    "(enter the same mark). Nothing renews automatically." % (w["mark"], exp, BUY_URL))
            ok, info = send_fn(email, "Your TM Watch for %s expires on %s" % (w["mark"], exp), text)
            if ok:
                sent[key] = today
            out.append((key, ok, info))
    return out


def run(watchlist, filings, today, out_dir=None, write=True, hits_out=None):
    """Pure core. Returns list of (sale_id, user, watch_mark, n_hits, path)."""
    results = []
    for sid, w in sorted(watchlist.items()):
        if w.get("expires") and w["expires"] < today:
            continue
        safe_user = "".join(c for c in w.get("user", "unknown")
                            if c.isalnum() or c in "-_") or "unknown"
        # expiry reminder promised on the landing page: one idempotent file
        # when ≤14 days remain (same filename each run -> git no-ops).
        if write and out_dir and w.get("expires"):
            try:
                ey, em, ed = map(int, w["expires"].split("-"))
                ty, tm, td = map(int, today.split("-"))
                left = (date(ey, em, ed) - date(ty, tm, td)).days
            except ValueError:
                left = 99
            if 0 <= left <= 14:
                d = os.path.join(out_dir, "alerts", safe_user)
                os.makedirs(d, exist_ok=True)
                with open(os.path.join(d, "expiry-reminder.md"), "w") as f:
                    f.write("# Your TM Watch for %s expires on %s\n\n"
                            "Renew for another year at "
                            "https://approj.gumroad.com/l/pwvfma (enter the same "
                            "mark and GitHub username).\n" % (w["mark"], w["expires"]))
        hits = hits_for(w["mark"], filings)
        if hits_out is not None:
            hits_out[sid] = hits
        if not hits:
            continue
        path = None
        if write and out_dir:
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
    tok = os.environ.get("GITHUB_ORG_TOKEN", "")
    if not os.path.isdir(os.path.join(ALERTS_DIR, ".git")):
        if not tok:
            print("watch_run: GITHUB_ORG_TOKEN missing, cannot clone alerts repo",
                  file=sys.stderr)
            return 1
        r = _git(["clone", "https://x-access-token:%s@github.com/%s/%s.git"
                  % (tok, OWNER, REPO), ALERTS_DIR], HERE)
        if r.returncode != 0:
            print("watch_run: clone failed: %s" % r.stderr.strip()[-400:],
                  file=sys.stderr)
            return 1
    hits_by_sid = {}
    results = run(watchlist, filings, today, out_dir=ALERTS_DIR, hits_out=hits_by_sid)
    total = sum(n for _s, _u, _m, n, _p in results)
    for sid, user, mark, n, path in results:
        print("watch_run: %s (%s) %r -> %d hit(s) -> %s" % (sid, user, mark, n, path))
    # EMAIL (primary channel). Idempotent via alerts_sent.json.
    sent = {}
    if os.path.exists(SENT):
        with open(SENT) as f:
            sent = json.load(f)
    if mailer.configured():
        acts = dispatch_emails(watchlist, results, today, sent, mailer.send, hits_by_sid)
        for key, ok, info in acts:
            print("watch_run: email %s %s — %s" % (key, "OK" if ok else "FAILED", info))
        with open(SENT, "w") as f:
            json.dump(sent, f, indent=1, sort_keys=True)
        n_fail = sum(1 for _k, ok, _i in acts if not ok)
        if n_fail:
            print("watch_run: %d EMAIL FAILURE(S) — subscribers missed alerts" % n_fail, file=sys.stderr)
    else:
        n_email = sum(1 for sid, *_r in results if watchlist[sid].get("email"))
        print("watch_run: mailer NOT configured — %d alert email(s) NOT sent (repo path only)" % n_email)
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
    # email dispatch: alert once per day per watch, expiry reminder once, idempotent
    for w in watchlist.values():
        w["email"] = w["user"] + "@example.com"
    watchlist["s2"]["expires"] = "2026-09-10"   # 9 days left -> reminder
    hb = {}
    res = run(watchlist, filings, "2026-09-01", write=False, hits_out=hb)
    calls = []

    def fake_send(to, subj, text, html=None):
        calls.append((to, subj))
        if html:   # alert (expiry reminders carry only the mailer footer rail)
            assert "Not legal advice" in text and "tsdr.uspto.gov" in text
            assert "<table" in html and "NYKE ATHLETICS" in html and "TSDR" in html
        return True, "ok"
    sent = {}
    acts = dispatch_emails(watchlist, res, "2026-09-01", sent, fake_send, hb)
    keys = sorted(k for k, ok, _i in acts if ok)
    assert keys == ["s1:2026-09-01", "s2:expiry"], keys
    assert calls[0][0] == "alice@example.com" and "2 similar marks to NIKE" in calls[0][1], calls
    assert calls[1][0] == "bob@example.com" and "expires on 2026-09-10" in calls[1][1], calls
    acts2 = dispatch_emails(watchlist, res, "2026-09-01", sent, fake_send, hb)
    assert acts2 == [] and len(calls) == 2, (acts2, calls)   # idempotent
    # failed send is NOT recorded as sent (retries next run)
    acts3 = dispatch_emails(watchlist, res, "2026-09-02", {}, lambda *a: (False, "boom"), hb)
    assert [ok for _k, ok, _i in acts3] == [False, False] and "s1:2026-09-02" not in sent
    html = render_alert_html("NIKE", "2026-09-01", hb["s1"])
    assert "<script" not in html and "pseudo-mark:" in html
    print("watch_run selftest: PASS (hit, pseudo-hit, non-hit, expiry, empty-day, email dispatch idempotent, html render)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    sys.exit(real_run(dry="--dry" in sys.argv))
