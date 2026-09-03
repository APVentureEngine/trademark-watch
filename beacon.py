#!/usr/bin/env python3
"""Anonymous page-load counter for a GitHub Pages site, with no account and
no third-party analytics service (c113).

WHY THIS EXISTS
GitHub Pages serves no logs and the GitHub traffic API counts github.com repo
views, NOT site visits — so until now the venture could not tell whether a
stranger had ever opened a page. Kill criterion 3 counts an organic traffic
spike as a signal, and we were measuring nothing.

HOW IT WORKS
Every generated page loads one 1x1 PNG from the public jsDelivr CDN:

    https://cdn.jsdelivr.net/gh/<owner>/<repo>@main/assets/px.png

jsDelivr publishes free, public, per-package daily request counts:

    https://data.jsdelivr.com/v1/stats/packages/gh/<owner>/<repo>?period=month

Those requests only happen when a browser renders one of our pages, so the
daily hit count is a lower bound on page loads (browsers cache the PNG for
jsDelivr's 12h TTL on @main, so a repeat visitor inside 12h counts once).
No cookies, no JS, no personal data, nothing for a visitor to consent to —
and the numbers are public, so a claim of "N page loads on date D" is
verifiable by anyone, which is exactly the property a traffic signal needs.

The file is served under our own repo, so this is not a tracking pixel owned
by anyone else: jsDelivr only ever sees an aggregate request count per file.
Every page carries a footer line saying so and linking the public stats URL.

BASELINE DISCIPLINE: our own curl checks also register as hits. Record the
count immediately after publishing and subtract it (see --stats).

Usage (cwd-independent):
    python3 beacon.py <site_dir> --repo owner/name          # inject (idempotent)
    python3 beacon.py <site_dir> --repo owner/name --check   # exit 1 if a page lacks it
    python3 beacon.py --stats --repo owner/name              # print daily hits
    python3 beacon.py --selftest
Stdlib only.
"""
import json
import os
import re
import sys
import urllib.request

CDN = "https://cdn.jsdelivr.net/gh/%s@main/assets/px.png"
STATS = "https://data.jsdelivr.com/v1/stats/packages/gh/%s?period=month"
# Private customer pages never get a third-party request: their visitor is a
# paying buyer and their URL is a secret. Also skip the retired rt/ client.
SKIP_DIRS = {".git", "node_modules", "alerts", "rt"}

_IMG_RE = re.compile(r'\n?<img src="https://cdn\.jsdelivr\.net/gh/[^"]+"[^>]*>\n?')
_NOTE_RE = re.compile(r'\n?<p class="beacon-note"[^>]*>.*?</p>\n?', re.S)
_BODY = re.compile(r'</body>', re.I)
_FOOTER = re.compile(r'</footer>', re.I)


def img_tag(repo):
    return ('<img src="%s" alt="" width="1" height="1" '
            'referrerpolicy="no-referrer" '
            'style="position:absolute;left:-9999px;top:0">' % (CDN % repo))


def note_tag(repo):
    return ('<p class="beacon-note" style="margin-top:.6rem;font-size:.8rem;'
            'color:#777">Page loads are counted anonymously by requesting one '
            '1&times;1 image from the public jsDelivr CDN — no cookies, no '
            'personal data, and the '
            '<a href="%s">daily totals are public</a>.</p>' % (STATS % repo))


def inject(html, repo):
    """Return (new_html, changed). Idempotent: strips any previous beacon
    first, so a repo rename or CDN change rewrites cleanly and a re-run of the
    generator produces byte-identical output (the daily refresh must not churn
    3,800 files)."""
    s = _IMG_RE.sub("", html)
    s = _NOTE_RE.sub("", s)
    if not _BODY.search(s):
        return html, False          # fragment, not a page
    if _FOOTER.search(s):
        s = _FOOTER.sub(note_tag(repo) + "\n</footer>", s, count=1)
    s = _BODY.sub(img_tag(repo) + "\n</body>", s, count=1)
    return s, s != html


def walk(site):
    for dp, dns, fns in os.walk(site):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith(".html"):
                yield os.path.join(dp, fn)


def run(site, repo, check=False):
    n = changed = missing = 0
    tag = img_tag(repo)
    for p in walk(site):
        n += 1
        s = open(p, encoding="utf-8").read()
        if check:
            if tag not in s:
                missing += 1
                if missing <= 5:
                    print("BEACON MISSING: " + os.path.relpath(p, site))
            continue
        out, ch = inject(s, repo)
        if ch:
            open(p, "w", encoding="utf-8").write(out)
            changed += 1
        if tag not in out:
            missing += 1
    if check:
        print("beacon check: %d page(s), %d missing" % (n, missing))
        return 1 if missing else 0
    print("beacon: %d page(s), %d changed, %d without tag" % (n, changed, missing))
    return 1 if missing else 0


def stats(repo):
    url = STATS % repo
    with urllib.request.urlopen(url, timeout=30) as r:
        d = json.load(r)
    hits = d.get("hits", {})
    dates = hits.get("dates", {})
    print("jsDelivr hits for %s (total %s)" % (repo, hits.get("total")))
    for day in sorted(dates)[-14:]:
        print("  %s  %s" % (day, dates[day]))
    return 0


def selftest():
    repo = "APVentureEngine/warn-act-notices"
    page = "<html><body><p>hi</p><footer>Sources: x</footer></body></html>"
    out, ch = inject(page, repo)
    assert ch and out.count("cdn.jsdelivr.net") == 1, out       # the pixel
    assert out.count("data.jsdelivr.com") == 1, out             # the public-stats link
    assert "px.png" in out and 'width="1"' in out
    assert out.index("beacon-note") < out.index("</footer>")
    assert out.index("<img src=") > out.index("</footer>")
    again, ch2 = inject(out, repo)
    assert again == out and not ch2, "not idempotent"
    # a repo change rewrites rather than duplicating
    other, ch3 = inject(out, "APVentureEngine/trademark-watch")
    assert ch3 and other.count("cdn.jsdelivr.net") == 1
    assert "warn-act-notices" not in other
    # fragments are left alone
    frag, ch4 = inject("<tr><td>x</td></tr>", repo)
    assert not ch4 and frag == "<tr><td>x</td></tr>"
    # a page with no footer still gets the pixel
    nf, ch5 = inject("<html><body>x</body></html>", repo)
    assert ch5 and "px.png" in nf and "beacon-note" not in nf
    print("beacon selftest OK")
    return 0


def main(argv):
    if "--selftest" in argv:
        return selftest()
    repo = None
    if "--repo" in argv:
        repo = argv[argv.index("--repo") + 1]
    if not repo:
        print("need --repo owner/name", file=sys.stderr)
        return 2
    if "--stats" in argv:
        return stats(repo)
    pos = [a for a in argv[1:] if not a.startswith("--") and a != repo]
    if not pos:
        print("need <site_dir>", file=sys.stderr)
        return 2
    return run(pos[0], repo, check="--check" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
