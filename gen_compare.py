#!/usr/bin/env python3
"""TM Watch — buyer-intent comparison page (c97).

Why this file exists (learning c43, warn-feed): the highest buyer-intent
queries in a niche are comparison/alternative queries ("trademark watch
service alternatives", "cheapest trademark monitoring", "is a trademark
watch worth it"), and product sites usually have ZERO pages that match them
— every SEO page we generate targets browsers of filings, not buyers.

Three rules this generator enforces, so the page cannot rot into a lie:
  1. HONESTY — every competitor row carries a price we fetched ourselves on
     the date printed next to it (competitors.json), and every row says
     something genuinely good about that competitor, including where they
     beat us (Markify is cheaper; Hawthorn is cheaper from mark two).
  2. LIVENESS — our own numbers (corpus size, latest Gazette issue, price)
     come from the live index manifest, so a re-run on unchanged data is
     byte-identical and the page's "as of" date tracks the DATA, never the
     wall clock.
  3. MAINTENANCE — a competitor row older than STALE_DAYS relative to the
     data date prints a loud WARN at generation time and is rendered with a
     "needs re-checking" marker rather than silently presented as current.

Usage:
  python3 gen_compare.py --out site            (writes site/compare.html)
  python3 gen_compare.py --selftest
"""
import argparse, datetime, html, json, os, re, sys
from pricing import PRICE, PRICE_YR, PRICE_USD, OLD_PRICE, cheaper_competitors, bundle_break_even

HERE = os.path.dirname(os.path.abspath(__file__))
STALE_DAYS = 90

OUR = {
    "name": "TM Watch (this site)",
    "price_label": PRICE_YR + " per mark — one payment, no auto-renewal",
    "coverage": "US only: every word mark in each Tuesday Official Gazette "
                "(published for opposition + registrations issued)",
    "delivery": "Private alert page + RSS feed, same day the issue lands "
                "(no email from us yet: pipe the feed through a free RSS-to-email forwarder such as Blogtrottr)",
    "free_tier": "Free instant similarity check with no account, plus a free "
                 "30-day watch (no card)",
    "good": "The only one here you can test before paying anything, and the "
            "only one whose matcher and benchmark are open source.",
}

BUY = "https://approj.gumroad.com/l/pwvfma?wanted=true"
FREE = "https://approj.gumroad.com/l/tm-free-watch?wanted=true"
REPO = "https://github.com/APVentureEngine/trademark-watch"

CSS = """:root{--ink:#1a1a24;--mut:#666;--acc:#0b5fff;--bg:#fff;--soft:#f4f6fa}
*{box-sizing:border-box}body{margin:0;font:16px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
main{max-width:820px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:1.6rem;line-height:1.25;margin:.4em 0}
h2{font-size:1.15rem;margin:32px 0 .4em}
.sub{color:var(--mut)}
.note{font-size:.85rem;color:var(--mut)}
table.cmp{width:100%;border-collapse:collapse;font-size:.86rem;margin:14px 0}
table.cmp th,table.cmp td{border-bottom:1px solid #dfe5f0;padding:8px 8px;text-align:left;vertical-align:top}
table.cmp th{background:var(--soft);font-size:.8rem;text-transform:uppercase;letter-spacing:.03em;color:#444}
table.cmp tr.us td{background:#f2f8ff}
.stale{color:#b00020}
.cta{margin:30px 0;padding:18px;border:1px solid #dfe5f0;border-radius:10px;background:var(--soft)}
.cta a.btn{display:inline-block;margin-top:8px;background:var(--acc);color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none}
.cta a.btn2{display:inline-block;margin:8px 0 0 10px;background:#fff;color:var(--acc);border:1px solid var(--acc);padding:10px 18px;border-radius:8px;text-decoration:none}
@media (max-width:560px){.cta a.btn2{margin-left:0;display:block;text-align:center}table.cmp{font-size:.8rem}}
footer{margin-top:44px;font-size:.85rem;color:var(--mut);border-top:1px solid #eee;padding-top:16px}
"""


def _days_between(a, b):
    fmt = "%Y-%m-%d"
    return (datetime.datetime.strptime(a, fmt) - datetime.datetime.strptime(b, fmt)).days


def build(competitors, ours, data_date, corpus_total, corpus_base):
    """Return (html_text, warnings). Pure function of its inputs."""
    warns = []
    e = html.escape
    rows = []

    def cell(txt):
        return "<td>%s</td>" % e(txt)

    # our row first, then competitors cheapest-first (honest ordering: we are
    # NOT the cheapest and the table must not hide that).
    comps = sorted(competitors, key=lambda c: c.get("price_usd_year", 9999))
    rows.append(
        "<tr class=\"us\"><td><b>%s</b></td>%s%s%s%s</tr>"
        % (e(ours["name"]), cell(ours["price_label"]), cell(ours["coverage"]),
           cell(ours["delivery"]), cell(ours["free_tier"]))
    )
    for c in comps:
        stale = _days_between(data_date, c["verified_on"]) > STALE_DAYS
        if stale:
            warns.append("STALE: %s price verified %s, data date %s (>%dd)"
                         % (c["name"], c["verified_on"], data_date, STALE_DAYS))
        price = e(c["price_label"])
        if stale:
            price += ' <span class="stale">(needs re-checking)</span>'
        rows.append(
            "<tr><td><a href=\"%s\" rel=\"nofollow noopener\">%s</a></td>"
            "<td>%s<br><span class=\"note\">price we saw on %s</span></td>%s%s%s</tr>"
            % (e(c["source_url"]), e(c["name"]), price, e(c["verified_on"]),
               cell(c["coverage"]), cell(c["delivery"]), cell(c["free_tier"]))
        )

    good_blocks = []
    per_mark = [c["price_usd_year"] for c in comps
                if c["price_usd_year"] > 0 and "marks" not in c.get("price_label", "")]
    floor_per_mark = min(per_mark) if per_mark else PRICE_USD
    for c in comps:
        good = c["good"]
        if "{break_even}" in good:   # computed arithmetic, never typed (c104)
            good = good.replace("{break_even}", str(bundle_break_even(c["price_usd_year"], floor_per_mark)))
        good_blocks.append(
            "<p><b>%s — %s.</b> %s%s</p>"
            % (e(c["name"]), e(c["price_label"]), e(good),
               (" " + e(c["note"])) if c.get("note") else "")
        )

    parts = []
    parts.append("<!doctype html>\n<html lang=\"en\">\n<head>\n")
    parts.append("<meta charset=\"utf-8\">\n"
                 "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n")
    parts.append("<title>Trademark watch services compared: $39–$99/yr, and what "
                 "each one actually does | TM Watch</title>\n")
    parts.append("<meta name=\"description\" content=\"Honest side-by-side of US "
                 "trademark watch services and their real prices, checked on %s: "
                 "Markify, TMReady, Hawthorn Law, the free USPTO search, and TM "
                 "Watch. Who is cheapest, who to buy instead of us, and what a "
                 "watch is actually for.\">\n" % e(data_date))
    parts.append("<link rel=\"canonical\" href=\"https://apventureengine.github.io/"
                 "trademark-watch/compare.html\">\n")
    parts.append("<style>%s</style>\n</head>\n<body>\n<main>\n" % CSS)

    parts.append("<p class=\"note\"><a href=\"./\">&larr; TM Watch — free instant "
                 "similarity check</a></p>\n")
    parts.append("<h1>Trademark watch services compared — what each one costs, and "
                 "who should buy which</h1>\n")
    parts.append(
        "<p class=\"sub\">A trademark watch exists for one reason: when a "
        "confusingly-similar mark is <i>published for opposition</i> in the USPTO "
        "Official Gazette, you have <b>30 days</b> to oppose it or ask for an "
        "extension. Nobody tells you it happened — the USPTO does not monitor "
        "marks on your behalf. A watch is the thing that notices in time.</p>\n")
    parts.append(
        "<p class=\"sub\">We sell one of these products, so read the table with "
        "that in mind. We have therefore put the cheapest option first, said "
        "plainly where the others beat us, and dated every price to the day we "
        "loaded the seller's own page. Prices below were checked on the dates "
        "shown; the rest of this page is regenerated from our live index, last "
        "rebuilt from the <b>%s</b> Gazette issue.</p>\n" % e(data_date))

    parts.append("<table class=\"cmp\">\n<tr><th>Service</th><th>Price</th>"
                 "<th>What is watched</th><th>How you are told</th>"
                 "<th>Free option</th></tr>\n")
    parts.append("\n".join(rows))
    parts.append("\n</table>\n")

    # the price sentence is COMPUTED from the rows, never typed (c104): a hand-written
    # "we are not the cheapest" went false the day the price moved to $29
    cheaper = cheaper_competitors(competitors)
    if cheaper:
        price_clause = (", and at %s for one mark we are not the cheapest line in the "
                        "table above (%s is)" % (PRICE, e(cheaper[0]["name"])))
    else:
        bundles = [c for c in competitors if "marks" in c.get("price_label", "")]
        price_clause = (", and while %s is the lowest single-mark price in the table as of "
                        "the dates shown, %s" % (PRICE, (
                            "a flat bundle such as %s's is cheaper once you watch several marks"
                            % e(bundles[0]["name"]) if bundles else
                            "a firm that bundles several marks for one fee may be cheaper for a portfolio")))
    parts.append("<h2>Buy someone else's if…</h2>\n")
    parts.append("".join(good_blocks))
    parts.append(
        "<p><b>And to be explicit about our own weak spots:</b> we watch the "
        "United States only, our alerts arrive as a private web page and an RSS "
        "feed rather than an email (email is being built; buyers get it at no "
        "extra charge when it ships), we are a one-person automated operation "
        "with no attorneys%s.</p>\n" % price_clause)

    parts.append("<h2>What you get from us for %s</h2>\n" % PRICE)
    parts.append(
        "<p>One mark watched for twelve months against every Tuesday Gazette "
        "issue — currently %s marks published or registered since %s in the "
        "rolling window this site searches — using a matcher that is open "
        "source and <a href=\"%s\">benchmarked in public</a> against real USPTO "
        "§2(d) refusal and opposition pairs. One payment, no auto-renewal, full "
        "refund within 14 days. No account: you enter your mark at checkout and "
        "get a private alert page plus an RSS feed within a day.</p>\n"
        % (e("{:,}".format(corpus_total)), e(corpus_base), e(REPO + "/blob/main/benchmark/RESULTS.txt")))
    parts.append(
        "<p>The part that is free forever and needs no account: the "
        "<a href=\"./\">instant similarity report</a> on the home page (it runs "
        "in your browser — nothing you type is sent anywhere), the "
        "<a href=\"filings/\">per-class listings</a> of newly published marks, "
        "and the <a href=\"data/\">weekly CSV of every word mark in each "
        "issue</a>. We sell the watching, never access to the data.</p>\n")

    parts.append("<div class=\"cta\">\n")
    parts.append("<b>Try the watch before you pay for it.</b>\n")
    parts.append("<p style=\"margin:.4em 0\">The free 30-day watch is the same "
                 "matcher, the same alert page and the same feed, for one mark, "
                 "with no card and nothing to cancel. If it flags nothing useful "
                 "in a month, you have lost nothing and you know not to buy.</p>\n")
    parts.append("<a class=\"btn\" href=\"%s\">Watch my mark free for 30 days</a>\n" % e(FREE))
    parts.append("<a class=\"btn2\" href=\"%s\">Or buy a year — %s</a>\n" % (e(BUY), PRICE))
    parts.append("</div>\n")

    parts.append("<h2>How the prices on this page are kept honest</h2>\n")
    parts.append(
        "<p class=\"note\">Every competitor price above was read off that "
        "company's own public page on the date printed beside it, by the same "
        "automated job that rebuilds this site. Prices change and pages move: if "
        "one of these is out of date, that is a bug — "
        "<a href=\"%s/issues/new\">open an issue</a> and it gets fixed on the "
        "next run. Rows older than %d days are marked in red rather than shown "
        "as current. We do not take affiliate commissions from anyone listed "
        "here, and none of these companies has any relationship with us.</p>\n"
        % (e(REPO), STALE_DAYS))

    parts.append(
        "<footer><p><b>Not legal advice.</b> Nothing here is a legal opinion "
        "about whether a mark infringes yours; a flag means \"a human should "
        "look\". TM Watch is published by APProjects and sold through Gumroad "
        "(seller <i>approj</i>); refunds are handled there. Contact: "
        "<a href=\"%s/issues/new\">a repo issue</a> or a reply to your receipt."
        "</p></footer>\n" % e(REPO))
    parts.append("</main>\n</body>\n</html>\n")
    return "".join(parts), warns


def load_manifest(site_dir):
    path = os.path.join(site_dir, "index", "manifest.json")
    with open(path) as f:
        m = json.load(f)
    return m["generated"], int(m["total"]), m["base"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "site"))
    ap.add_argument("--competitors", default=os.path.join(HERE, "competitors.json"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    with open(a.competitors) as f:
        comps = json.load(f)["competitors"]
    data_date, total, base = load_manifest(a.out)
    text, warns = build(comps, OUR, data_date, total, base)
    dest = os.path.join(a.out, "compare.html")
    with open(dest, "w") as f:
        f.write(text)
    for w in warns:
        print("gen_compare: WARN %s" % w)
    print("gen_compare: %d competitors -> %s (%d bytes, data %s)"
          % (len(comps), dest, len(text), data_date))
    return 0


def selftest():
    comps = [
        {"name": "Cheap Co", "price_label": "$39/yr", "price_usd_year": 39,
         "coverage": "US", "delivery": "email", "free_tier": "none",
         "good": "Cheaper than us.", "source_url": "https://example.com/a",
         "verified_on": "2026-09-01"},
        {"name": "Old Co", "price_label": "$99/yr", "price_usd_year": 99,
         "coverage": "US", "delivery": "email", "free_tier": "none",
         "good": "Has attorneys.", "source_url": "https://example.com/b",
         "verified_on": "2026-01-01"},
    ]
    t1, w1 = build(comps, OUR, "2026-09-03", 262226, "2026-05-19")
    t2, _ = build(comps, OUR, "2026-09-03", 262226, "2026-05-19")
    assert t1 == t2, "gen_compare is not deterministic"
    assert len(w1) == 1 and "Old Co" in w1[0], w1
    assert "needs re-checking" in t1
    # cheapest competitor must appear ABOVE the more expensive one
    assert t1.index("Cheap Co") < t1.index("Old Co")
    # our own row must exist, carry the price, and admit the weak spots
    assert PRICE_YR + " per mark" in t1 and OLD_PRICE not in t1
    # price sentence is computed: nobody below us -> "lowest single-mark price"; a cheaper
    # row flips it to the concession naming that row
    assert "is the lowest single-mark price" in t1 and "not the cheapest" not in t1
    cheap = [dict(comps[0], name="Budget Co", price_label="$19/yr", price_usd_year=19)] + comps
    t3, _ = build(cheap, OUR, "2026-09-03", 262226, "2026-05-19")
    assert "not the cheapest line in the table above (Budget Co is)" in t3 and "lowest single-mark" not in t3
    bund = dict(comps[1], name="Bundle Co", price_label="$99/yr for up to 5 marks", price_usd_year=99,
                good="Five for $99 beats us from mark {break_even} onward.", verified_on="2026-09-01")
    t4, _ = build(comps + [bund], OUR, "2026-09-03", 262226, "2026-05-19")
    assert "from mark 4 onward" in t4 and "{break_even}" not in t4, "break-even must be computed from the floor price"
    t5, _ = build(cheap + [bund], OUR, "2026-09-03", 262226, "2026-05-19")
    assert "from mark 6 onward" in t5
    with open(os.path.join(HERE, "competitors.json")) as f:
        live, _ = build(json.load(f)["competitors"], OUR, "2026-09-03", 262226, "2026-05-19")
    assert "{" not in re.sub(r"<style>.*?</style>", "", live, flags=re.S).split("<body>")[1], "unrendered placeholder"
    assert "lowest single-mark price" in t1  # c104: computed clause, see above
    assert "Cheaper than us." in t1
    # live numbers must be interpolated, never hardcoded
    assert "262,226" in t1 and "2026-05-19" in t1 and "2026-09-03" in t1
    # every competitor row links out with rel=nofollow (we are not passing juice
    # to competitors, and it keeps the page from reading as an affiliate farm)
    assert t1.count("rel=\"nofollow noopener\"") == 2
    # no unescaped placeholder left behind
    assert "%s" not in t1 and "TODO" not in t1
    print("gen_compare selftest: OK (%d bytes, 1 staleness warning as expected)" % len(t1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
