#!/usr/bin/env python3
"""SEO surfaces from marks.jsonl: per-class recent-filings pages + sitemap.

Output (into site/, alongside index.html/report.js):
  site/filings/index.html        latest-window overview: counts by class,
                                 newest filings table, JSON-LD Dataset
  site/filings/class-<NN>.html   recent filings in intl class NN (1..45),
                                 newest first, capped at MAX_ROWS
  site/sitemap.xml               report page + all filings pages

Deterministic: "updated" stamps come from the newest filing_date in the DATA,
never the wall clock. Honest framing: pages say what the data is (USPTO daily
application files) and are only ever pushed in REAL mode (refresh.sh rail).

Usage: python3 gen_seo.py --in marks.jsonl --out site [--base URL]
Stdlib only.
"""
import html
import json
import os
import sys

BASE_DEFAULT = "https://approj.github.io/trademark-watch"
MAX_ROWS = 200
RECENT_DAYS = 14  # overview table window

CLASS_NAMES = {
    1: "Chemicals", 2: "Paints", 3: "Cosmetics & cleaning", 4: "Lubricants & fuels",
    5: "Pharmaceuticals", 6: "Metal goods", 7: "Machinery", 8: "Hand tools",
    9: "Electronics & software", 10: "Medical devices", 11: "Appliances",
    12: "Vehicles", 13: "Firearms", 14: "Jewelry", 15: "Musical instruments",
    16: "Paper & printed goods", 17: "Rubber & plastics", 18: "Leather goods",
    19: "Building materials", 20: "Furniture", 21: "Housewares", 22: "Ropes & textiles raw",
    23: "Yarns & threads", 24: "Fabrics", 25: "Clothing & footwear", 26: "Lace & trimmings",
    27: "Carpets", 28: "Toys & sporting goods", 29: "Meats & processed foods",
    30: "Staple foods", 31: "Fresh produce", 32: "Beers & beverages", 33: "Wines & spirits",
    34: "Tobacco", 35: "Advertising & business services", 36: "Financial services",
    37: "Construction & repair", 38: "Telecommunications", 39: "Transport & storage",
    40: "Material treatment", 41: "Education & entertainment", 42: "Scientific & tech services",
    43: "Food & lodging services", 44: "Medical & beauty services", 45: "Legal & security services",
}

STYLE = ("body{font:16px/1.5 -apple-system,Segoe UI,sans-serif;max-width:860px;"
         "margin:2rem auto;padding:0 1rem;color:#1a1a1a}table{border-collapse:"
         "collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:.4rem "
         ".5rem;text-align:left;font-size:14px}a{color:#0b62d6}h1{font-size:1.5rem}"
         ".note{color:#555;font-size:13px}.cta{background:#0b62d6;color:#fff;"
         "padding:.5rem 1rem;border-radius:6px;text-decoration:none;display:"
         "inline-block;margin:.5rem 0}")

def cta(base):
    return ('<p><a class="cta" href="%s/">Run a free instant similarity check '
            'on your mark</a> &nbsp; <a href="https://approj.gumroad.com/l/pwvfma">'
            'Automated daily watch — $49/yr</a></p>' % base)

FOOT = ('<p class="note">Source: USPTO trademark daily application XML files '
        '(TRTDXFAP), regenerated daily. Informational only — not legal advice, '
        'no opinion on likelihood of confusion. '
        '<a href="https://github.com/APProj/trademark-watch">Data pipeline is '
        'open source.</a></p>')


def esc(s):
    return html.escape(str(s), quote=True)


def page(title, body_html, base, canonical, jsonld=None):
    ld = ('<script type="application/ld+json">%s</script>'
          % json.dumps(jsonld, sort_keys=True)) if jsonld else ""
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            '<meta name=viewport content="width=device-width,initial-scale=1">'
            "<title>%s</title><link rel=canonical href=\"%s\">%s<style>%s</style>"
            "</head><body>%s%s</body></html>"
            % (esc(title), esc(canonical), ld, STYLE,
               body_html, FOOT))


def row_html(r):
    return ("<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (r["serial"], esc(r["mark"]), r["filing_date"],
               " ".join(str(c) for c in r.get("classes", [])) or "—"))


def build(rows, out_dir, base):
    fdir = os.path.join(out_dir, "filings")
    os.makedirs(fdir, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["filing_date"], r["serial"]), reverse=True)
    newest = rows[0]["filing_date"] if rows else "n/a"
    urls = [base + "/", base + "/filings/"]

    # per-class pages
    by_class = {}
    for r in rows:
        for c in r.get("classes", []):
            by_class.setdefault(c, []).append(r)
    for c in range(1, 46):
        crows = by_class.get(c, [])[:MAX_ROWS]
        cname = CLASS_NAMES.get(c, "")
        title = ("New trademark filings — Class %d (%s) — updated %s"
                 % (c, cname, newest))
        body = ("<h1>New USPTO trademark filings — Class %d: %s</h1>"
                "<p class=note>Most recent %d application(s) in international "
                "class %d from USPTO daily XML, as of %s.</p>%s"
                "<table><tr><th>Serial</th><th>Mark</th><th>Filed</th>"
                "<th>Classes</th></tr>%s</table>"
                % (c, esc(cname), len(crows), c, newest, cta(base),
                   "".join(row_html(r) for r in crows)
                   or "<tr><td colspan=4>No recent filings parsed.</td></tr>"))
        with open(os.path.join(fdir, "class-%02d.html" % c), "w") as f:
            f.write(page(title, body, base, "%s/filings/class-%02d.html" % (base, c)))
        urls.append("%s/filings/class-%02d.html" % (base, c))

    # overview page
    recent = [r for r in rows if r["filing_date"] >= _minus_days(newest, RECENT_DAYS)]
    counts = sorted(((len(v), c) for c, v in by_class.items()), reverse=True)[:10]
    body = ("<h1>New US trademark filings — daily-updated</h1>"
            "<p>%d applications in the current window; newest filing date %s. "
            "Top classes: %s.</p>%s"
            "<h2>Browse by class</h2><p>%s</p>"
            "<h2>Latest filings (last %d days, first %d)</h2>"
            "<table><tr><th>Serial</th><th>Mark</th><th>Filed</th><th>Classes</th></tr>%s</table>"
            % (len(rows), newest,
               ", ".join("<a href=\"class-%02d.html\">%d (%s, %d)</a>"
                         % (c, c, esc(CLASS_NAMES.get(c, "")), n) for n, c in counts[:5]),
               cta(base),
               " · ".join("<a href=\"class-%02d.html\">%d</a>" % (c, c)
                          for c in range(1, 46)),
               RECENT_DAYS, MAX_ROWS,
               "".join(row_html(r) for r in recent[:MAX_ROWS])))
    jsonld = {"@context": "https://schema.org", "@type": "Dataset",
              "name": "US trademark application filings (daily)",
              "description": "Daily-updated normalized feed of new USPTO "
                             "trademark applications with similarity search.",
              "url": base + "/filings/", "isAccessibleForFree": True,
              "dateModified": newest,
              "creator": {"@type": "Organization", "name": "TM Watch"}}
    with open(os.path.join(fdir, "index.html"), "w") as f:
        f.write(page("New US trademark filings by class — updated %s" % newest,
                     body, base, base + "/filings/", jsonld))

    with open(os.path.join(out_dir, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + "".join("<url><loc>%s</loc><lastmod>%s</lastmod></url>\n"
                          % (esc(u), newest) for u in urls)
                + "</urlset>\n")
    return len(urls)


def _minus_days(iso, n):
    from datetime import date, timedelta
    y, m, d = map(int, iso.split("-"))
    return (date(y, m, d) - timedelta(days=n)).isoformat()


def main(argv):
    src = argv[argv.index("--in") + 1] if "--in" in argv else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "marks.jsonl")
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "site")
    base = argv[argv.index("--base") + 1] if "--base" in argv else BASE_DEFAULT
    rows = []
    with open(src) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    n = build(rows, out, base)
    print("gen_seo: %d rows -> %d sitemap URLs in %s" % (len(rows), n, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
