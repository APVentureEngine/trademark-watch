#!/usr/bin/env python3
"""Private alert pages: one unlisted page + RSS feed per paid watch (c84).

Why: the Gumroad checkout REQUIRES a GitHub username (custom fields are not
editable via API) and email delivery has no key (A014). The site review said
the declared buyer (SMB brand owner) bounces at "GitHub username". This is
the delivery channel that needs NO account, NO email key and NO human:

  slug = sha256("tmwatch|" + MARK + "|" + email)[:32]
    MARK  = watched mark, upper-cased, whitespace collapsed, trimmed
    email = purchase email, lower-cased, trimmed
  page  = <site>/alerts/<slug>/            (HTML, noindex, not in sitemap)
  feed  = <site>/alerts/<slug>/feed.xml    (RSS: one item per alert day)

The buyer opens <site>/alerts/, types the mark + purchase email; the browser
computes the same SHA-256 (WebCrypto) and jumps to the page. The URL is
unlisted, but the hosting repo is PUBLIC (its tree lists every slug), so the
page holds only the watched mark and public USPTO records — never name or
email — and says so. Upgrade path (BACKLOG): client-side AES-GCM with a key
derived from mark|email so the repo holds only ciphertext.

Inputs:  watchlist.json (fulfill.py), alert_history.json (watch_run.py:
         {sid: {"checked": [days], "days": {day: [hit, ...]}}}).
Output:  <out>/alerts/index.html (finder) + <out>/alerts/<slug>/{index.html,
         feed.xml} for every watch; stale slug dirs are removed.
Usage:   python3 gen_alert_pages.py [--out site] [--selftest]
Stdlib only. Never prints emails.
"""
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
WATCHLIST = os.path.join(HERE, "watchlist.json")
HISTORY = os.path.join(HERE, "alert_history.json")
SITE = "https://apventureengine.github.io/trademark-watch/"
BUY_URL = "https://approj.gumroad.com/l/pwvfma"
DISCLAIMER = ("Automated similarity flags for human review. Not legal advice; no "
              "opinion on likelihood of confusion. Verify at the TSDR link.")


def norm_mark(m):
    return " ".join(str(m).upper().split())


def norm_email(e):
    return str(e).strip().lower()


def slug(mark, email):
    s = "tmwatch|%s|%s" % (norm_mark(mark), norm_email(email))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:32]


def _h(x):
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def tsdr(serial):
    return ("https://tsdr.uspto.gov/#caseNumber=%s&caseType=SERIAL_NO"
            "&searchType=statusSearch" % serial)


CSS = ("body{font:16px/1.5 system-ui,sans-serif;max-width:880px;margin:2rem auto;padding:0 1rem;"
       "color:#1a1a1a}table{border-collapse:collapse;width:100%;font-size:14px}"
       "td,th{border:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}"
       "th{background:#f4f4f4}.tw{overflow-x:auto}.note{color:#555;font-size:14px}"
       "input{font:inherit;padding:.4rem;width:100%;box-sizing:border-box;margin:.2rem 0 .8rem}"
       "button{font:inherit;padding:.5rem 1rem}.ok{background:#e8f6ea;padding:.6rem 1rem;border-radius:6px}")


def render_page(w, hist, today):
    mark = w["mark"]
    expires = w.get("expires") or ""
    expired = bool(expires) and expires < today
    checked = sorted(set(hist.get("checked", [])))
    days = hist.get("days", {})
    parts = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
             "<meta name=\"robots\" content=\"noindex,nofollow,noarchive\">",
             "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
             "<title>TM Watch — alerts for %s</title>" % _h(mark),
             "<link rel=\"alternate\" type=\"application/rss+xml\" title=\"TM Watch alerts — %s\" href=\"feed.xml\">"
             % _h(mark), "<style>%s</style></head><body>" % CSS,
             "<h1>TM Watch — %s</h1>" % _h(mark)]
    if expired:
        parts.append("<p><b>This watch expired on %s.</b> The alert history below stays online; "
                     "<a href=\"%s\">renew for another year</a> (enter the same mark and purchase "
                     "email so this page keeps working).</p>" % (expires, BUY_URL))
    else:
        parts.append("<p class=\"ok\">Watch active until <b>%s</b> (one-time payment, no auto-renewal). "
                     "Bookmark this page or subscribe to its <a href=\"feed.xml\">RSS feed</a> — "
                     "a new entry appears here every Tuesday a USPTO Official Gazette issue contains "
                     "a similar mark. Quiet weeks add a line to the checked list, nothing else.</p>"
                     % expires)
    parts.append("<p class=\"note\">A mark <i>published for opposition</i> can be opposed (or an "
                 "extension requested) for 30 days from its Gazette date. %s</p>" % DISCLAIMER)
    if not days:
        parts.append("<h2>No similar filings so far</h2>")
    for day in sorted(days, reverse=True):
        hits = days[day]
        parts.append("<h2 id=\"%s\">%s — %d similar mark(s)</h2><div class=\"tw\"><table>"
                     "<tr><th>Serial</th><th>Mark</th><th>Gazette date</th><th>Event</th>"
                     "<th>Classes</th><th>Why flagged</th><th>Status</th></tr>" % (day, day, len(hits)))
        for h in sorted(hits, key=lambda x: x.get("serial", 0)):
            parts.append("<tr><td>%s</td><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                         "<td><a href=\"%s\">TSDR</a></td></tr>" % (
                             _h(h.get("serial", "")), _h(h.get("mark", "")), _h(h.get("date", "")),
                             _h(h.get("event", "")), _h(h.get("classes", "") or "—"),
                             _h(h.get("reasons", "")), tsdr(h.get("serial", ""))))
        parts.append("</table></div>")
    parts.append("<h2>Issues checked</h2><p class=\"note\">%s</p>" % (
        ", ".join(checked) if checked else
        "none yet — the first check runs with the next Gazette issue (Tuesdays)."))
    parts.append("<p class=\"note\">Privacy, plainly: this page is unlisted (not indexed, not linked, not in "
                 "the sitemap) and its address is derived from your purchase email, but the site is served "
                 "from a public GitHub repository, so anyone browsing that repository can see it. It "
                 "therefore holds only your watched mark and public USPTO records — never your name or "
                 "email. Lost the link? Rebuild it at "
                 "<a href=\"../\">%salerts/</a>. Questions: reply to your Gumroad receipt or "
                 "<a href=\"https://github.com/APVentureEngine/trademark-watch/issues/new\">open an issue</a>. "
                 "Run by APProjects (Gumroad seller <i>approj</i>).</p></body></html>" % SITE)
    return "".join(parts)


def render_feed(w, hist, s):
    mark = w["mark"]
    base = "%salerts/%s/" % (SITE, s)
    items = []
    for day in sorted(hist.get("days", {}), reverse=True):
        hits = hist["days"][day]
        desc = "; ".join("%s %s (%s)" % (h.get("serial", ""), h.get("mark", ""), h.get("reasons", ""))
                         for h in sorted(hits, key=lambda x: x.get("serial", 0)))
        items.append("<item><title>%s — %d similar mark(s) in the %s Gazette check</title>"
                     "<link>%s#%s</link><guid isPermaLink=\"true\">%s#%s</guid>"
                     "<pubDate>%s</pubDate><description>%s</description></item>"
                     % (_h(mark), len(hits), day, base, day, base, day, _rfc822(day), _h(desc)))
    return ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel>"
            "<title>TM Watch alerts — %s</title><link>%s</link><description>Similar-mark alerts "
            "from weekly USPTO Official Gazette issues for the watched mark %s. %s</description>"
            "%s</channel></rss>" % (_h(mark), base, _h(mark), _h(DISCLAIMER), "".join(items)))


def _rfc822(day):
    try:
        y, m, d = map(int, day.split("-"))
        dt = date(y, m, d)
        return dt.strftime("%a, %d %b %Y 12:00:00 +0000")
    except ValueError:
        return day


FINDER = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="robots" content="noindex,nofollow"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TM Watch — open your private alert page</title><style>%s</style></head><body>
<h1>Open your private alert page</h1>
<p>Bought a <a href="%s">TM Watch</a>? Type the mark exactly as you entered it at checkout and the
email you paid with. Nothing is sent anywhere: your browser computes the page address locally
(SHA-256) and jumps to it. Your page never shows your name or email — only the watched mark and
public USPTO records — because the site is hosted from a public repository.</p>
<form id="f"><label>Watched mark<input id="m" autocomplete="off" required></label>
<label>Purchase email<input id="e" type="email" autocomplete="email" required></label>
<button type="submit">Open my alerts</button></form>
<p id="out" class="note"></p>
<p class="note">Your page is created within 24 hours of purchase (the pipeline runs daily). If it shows
"not found" after that, reply to your Gumroad receipt with the mark you entered — the operator sees
it directly. The page has an RSS feed; subscribe to it in any feed reader to be notified.
Run by APProjects (Gumroad seller <i>approj</i>). <a href="../">Back to the free checker</a>.</p>
<script>
function normMark(m){return m.toUpperCase().split(/\\s+/).filter(Boolean).join(' ');}
function normEmail(e){return e.trim().toLowerCase();}
async function slugFor(m,e){
  var s='tmwatch|'+normMark(m)+'|'+normEmail(e);
  var buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(function(b){return ('0'+b.toString(16)).slice(-2);}).join('').slice(0,32);
}
document.getElementById('f').addEventListener('submit',async function(ev){
  ev.preventDefault();
  var m=document.getElementById('m').value, e=document.getElementById('e').value;
  if(!m.trim()||!e.trim()){return;}
  var s=await slugFor(m,e);
  var url=s+'/';
  document.getElementById('out').innerHTML='Opening <a href="'+url+'">'+url+'</a> …';
  location.href=url;
});
</script></body></html>"""


def build(watchlist, history, out_dir, today):
    adir = os.path.join(out_dir, "alerts")
    os.makedirs(adir, exist_ok=True)
    with open(os.path.join(adir, "index.html"), "w") as f:
        f.write(FINDER % (CSS, BUY_URL))
    keep = set()
    n = 0
    for sid, w in sorted(watchlist.items()):
        if not w.get("mark") or not w.get("email"):
            continue
        s = slug(w["mark"], w["email"])
        keep.add(s)
        d = os.path.join(adir, s)
        os.makedirs(d, exist_ok=True)
        hist = history.get(sid, {})
        with open(os.path.join(d, "index.html"), "w") as f:
            f.write(render_page(w, hist, today))
        with open(os.path.join(d, "feed.xml"), "w") as f:
            f.write(render_feed(w, hist, s))
        n += 1
    for name in os.listdir(adir):
        p = os.path.join(adir, name)
        if os.path.isdir(p) and name not in keep:
            shutil.rmtree(p)
    return n


def selftest():
    import xml.dom.minidom
    assert slug(" kodiak  coffee ", "A@B.com") == slug("KODIAK COFFEE", "a@b.com")
    assert slug("KODIAK COFFEE", "a@b.com") != slug("KODIAK COFFEE", "c@b.com")
    assert len(slug("x", "y@z")) == 32
    # normalisation parity with the finder page's JS (quickjs, if installed)
    try:
        import quickjs
        ctx = quickjs.Context()
        ctx.eval("function normMark(m){return m.toUpperCase().split(/\\s+/).filter(Boolean).join(' ');}"
                 "function normEmail(e){return e.trim().toLowerCase();}")
        for m, e in [(" kodiak  coffee ", " A@B.com "), ("Lumina\tSkin", "X@Y.ORG"), ("ÉCLAT", "u@v.w")]:
            assert ctx.eval("normMark(%s)" % json.dumps(m)) == norm_mark(m), m
            assert ctx.eval("normEmail(%s)" % json.dumps(e)) == norm_email(e), e
        js_ok = True
    except ImportError:
        js_ok = False
    tmp = tempfile.mkdtemp()
    try:
        wl = {"s1": {"mark": "Kodiak Coffee", "email": "a@b.com", "user": None,
                     "start": "2026-09-02T00:00:00Z", "expires": "2027-09-02"},
              "s2": {"mark": "Old Mark", "email": "o@b.com", "user": None,
                     "start": "2025-01-01T00:00:00Z", "expires": "2026-01-01"}}
        hist = {"s1": {"checked": ["2026-09-01", "2026-09-08"],
                       "days": {"2026-09-08": [{"serial": 99000001, "mark": "KODIAC BREW",
                                               "date": "2026-09-08", "event": "Published for opposition",
                                               "classes": "30", "reasons": "rare-token KODIAK~KODIAC"}]}}}
        n = build(wl, hist, tmp, "2026-09-09")
        assert n == 2
        s1 = slug("Kodiak Coffee", "a@b.com")
        page = open(os.path.join(tmp, "alerts", s1, "index.html")).read()
        assert "KODIAC BREW" in page and "noindex" in page and "Watch active until <b>2027-09-02" in page
        assert "a@b.com" not in page, "email must never appear on the page"
        feed = open(os.path.join(tmp, "alerts", s1, "feed.xml")).read()
        xml.dom.minidom.parseString(feed)
        assert "1 similar mark(s)" in feed
        s2 = slug("Old Mark", "o@b.com")
        p2 = open(os.path.join(tmp, "alerts", s2, "index.html")).read()
        assert "expired on 2026-01-01" in p2 and "No similar filings so far" in p2
        assert os.path.exists(os.path.join(tmp, "alerts", "index.html"))
        # stale dir removal
        os.makedirs(os.path.join(tmp, "alerts", "deadbeef"))
        build({"s1": wl["s1"]}, hist, tmp, "2026-09-09")
        assert not os.path.exists(os.path.join(tmp, "alerts", "deadbeef"))
        assert not os.path.exists(os.path.join(tmp, "alerts", s2))
    finally:
        shutil.rmtree(tmp)
    print("gen_alert_pages selftest PASS (js parity %s)" % ("checked" if js_ok else "skipped"))
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    out = "site"
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    out = os.path.join(HERE, out) if not os.path.isabs(out) else out
    wl = json.load(open(WATCHLIST)) if os.path.exists(WATCHLIST) else {}
    hist = json.load(open(HISTORY)) if os.path.exists(HISTORY) else {}
    n = build(wl, hist, out, date.today().isoformat())
    print("gen_alert_pages: %d private alert page(s) + finder written to %s/alerts/" % (n, out))


if __name__ == "__main__":
    main()
