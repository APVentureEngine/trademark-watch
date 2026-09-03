#!/usr/bin/env python3
"""gen_guides.py — buyer-intent explainer pages (c98).

The compare page (c97) is the only page that answers a *shopping* query. The
next thing a mark owner searches is procedural: "my trademark was published
for opposition, what happens now", "how long is the opposition period",
"how much does it cost to oppose a trademark". Those queries are what a watch
is FOR, so each guide ends in the free watch CTA. Everything numeric comes
from FACTS below (USPTO fee schedule, with the day we read it); like
competitors.json, a fact older than STALE_DAYS renders a red "(needs
re-checking)" marker and prints a WARN so the page never silently rots.

  python3 gen_guides.py --out site      # writes site/opposition-window.html
  python3 gen_guides.py --selftest
"""
import argparse, datetime, html, json, os, re, sys
from pricing import PRICE, PRICE_YR, PRICE_USD, OLD_PRICE, cheaper_competitors, bundle_break_even

HERE = os.path.dirname(os.path.abspath(__file__))
STALE_DAYS = 90
BASE = "https://apventureengine.github.io/trademark-watch"
REPO = "https://github.com/APVentureEngine/trademark-watch"
FREE = "https://approj.gumroad.com/l/tm-free-watch?wanted=true"
BUY = "https://approj.gumroad.com/l/pwvfma?wanted=true"

# Every number on the page. verified_on = the day we read it off the source.
FACTS = {
    "fee_schedule": {
        "source_url": "https://www.uspto.gov/learning-and-resources/fees-and-payment/uspto-fee-schedule",
        "effective": "2025-01-19",
        "verified_on": "2026-09-03",
        "opposition_per_class_electronic": 600,
        "opposition_per_class_paper": 700,
        "cancellation_per_class_electronic": 600,
        "ext_first_30_days": 0,
        "ext_90_days_or_second_60": 200,
        "ext_final_60_days": 400,
    },
    "period": {
        "source_url": "https://www.uspto.gov/trademarks/trademark-trial-and-appeal-board/filing-ttab",
        "verified_on": "2026-09-03",
        "opposition_days": 30,
    },
    "gazette": {
        "source_url": "https://www.uspto.gov/learning-and-resources/official-gazette",
        "verified_on": "2026-09-03",
        "cadence": "every Tuesday",
    },
}

CSS = """:root{--ink:#1a1a24;--mut:#666;--acc:#0b5fff;--bg:#fff;--soft:#f4f6fa}
*{box-sizing:border-box}body{margin:0;font:16px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:var(--ink);background:var(--bg)}
main{max-width:820px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:1.6rem;line-height:1.25;margin:.4em 0}
h2{font-size:1.15rem;margin:32px 0 .4em}
.sub,.note{color:var(--mut)}.note{font-size:.85rem}
table.f{width:100%;border-collapse:collapse;font-size:.9rem;margin:14px 0}
table.f th,table.f td{border-bottom:1px solid #dfe5f0;padding:8px;text-align:left;vertical-align:top}
table.f th{background:var(--soft);font-size:.8rem;text-transform:uppercase;letter-spacing:.03em;color:#444}
.stale{color:#b00020}
ol.steps li{margin:.5em 0}
.cta{margin:30px 0;padding:18px;border:1px solid #dfe5f0;border-radius:10px;background:var(--soft)}
.cta a.btn{display:inline-block;margin-top:8px;background:var(--acc);color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none}
.cta a.btn2{display:inline-block;margin:8px 0 0 10px;background:#fff;color:var(--acc);border:1px solid var(--acc);padding:10px 18px;border-radius:8px;text-decoration:none}
@media (max-width:560px){.cta a.btn2{margin-left:0;display:block;text-align:center}}
footer{margin-top:44px;font-size:.85rem;color:var(--mut);border-top:1px solid #eee;padding-top:16px}
"""


def e(s):
    return html.escape(str(s), quote=True)


def _days_between(a, b):
    da = datetime.date.fromisoformat(a)
    db = datetime.date.fromisoformat(b)
    return (db - da).days


def _stale(fact, data_date, warns, label):
    if _days_between(fact["verified_on"], data_date) > STALE_DAYS:
        warns.append("%s verified %s is older than %d days" % (label, fact["verified_on"], STALE_DAYS))
        return ' <span class="stale">(needs re-checking)</span>'
    return ""


def usd(n):
    return "$0 (no fee)" if n == 0 else "${:,}".format(n)


def build_opposition_window(facts, data_date, corpus_total, corpus_base):
    warns = []
    fs = facts["fee_schedule"]
    pd = facts["period"]
    fee_stale = _stale(fs, data_date, warns, "fee schedule")
    per_stale = _stale(pd, data_date, warns, "opposition period")
    days = pd["opposition_days"]

    p = []
    p.append("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n")
    p.append("<title>Your trademark was published for opposition — what happens in the "
             "%d-day window (and what it costs to oppose) | TM Watch</title>\n" % days)
    p.append("<meta name=\"description\" content=\"Plain-English timeline of the USPTO "
             "%d-day opposition period after a mark is published in the Official Gazette: "
             "who can oppose, the extension deadlines, current TTAB fees (%s per class "
             "electronic), and how to find out the same week whether a similar mark was "
             "published against yours.\">\n" % (days, usd(fs["opposition_per_class_electronic"])))
    p.append("<link rel=\"canonical\" href=\"%s/opposition-window.html\">\n" % BASE)
    p.append("<style>%s</style>\n</head>\n<body>\n<main>\n" % CSS)
    p.append("<p class=\"note\"><a href=\"./\">&larr; TM Watch — free instant similarity check</a></p>\n")
    p.append("<h1>Your mark was published for opposition. Here is what the next %d days look like.</h1>\n" % days)
    p.append(
        "<p class=\"sub\">Every Tuesday the USPTO publishes a new issue of the "
        "<i>Trademark Official Gazette</i>. Being listed in it is good news — the "
        "examining attorney has approved your application — but it also opens a "
        "fixed window in which anyone who believes they would be harmed by your "
        "registration can file to stop it. The same window is your chance to stop "
        "someone else's confusingly-similar mark. This page explains the mechanics "
        "with the numbers taken from the USPTO's own fee schedule, dated to the day "
        "we read it. It is not legal advice.</p>\n")

    p.append("<h2>The timeline</h2>\n<ol class=\"steps\">\n")
    p.append("<li><b>Day 0 — publication.</b> Your mark appears in that week's "
             "Official Gazette issue (applications section). Your TSDR status "
             "changes to <i>published for opposition</i>. Nothing is mailed to "
             "competitors; the only way anyone learns about it is by reading the "
             "issue or running a watch.</li>\n")
    p.append("<li><b>Days 1–%d — the opposition period.</b>%s Any person or company "
             "that believes it would be damaged by the registration may file a "
             "<i>notice of opposition</i> with the Trademark Trial and Appeal Board "
             "(TTAB), or ask for more time to decide.</li>\n" % (days, per_stale))
    p.append("<li><b>Extensions.</b> A potential opposer can ask for extra time before "
             "the %d days run out. The first %d-day extension is granted on request "
             "(%s); a further request up to 90 days from the original deadline costs "
             "%s; a final 60-day request, which needs consent or extraordinary "
             "circumstances, costs %s.%s The total is capped at 180 days from the "
             "publication date.</li>\n"
             % (days, 30, usd(fs["ext_first_30_days"]), usd(fs["ext_90_days_or_second_60"]),
                usd(fs["ext_final_60_days"]), fee_stale))
    p.append("<li><b>If nobody opposes.</b> A use-based application (or one that "
             "has already shown use) proceeds to registration; an intent-to-use "
             "application gets a Notice of Allowance and you then have to prove "
             "use. Either way the window closes quietly — you will not be told "
             "that nobody objected.</li>\n")
    p.append("<li><b>If somebody opposes.</b> The TTAB opens a proceeding that "
             "looks like a slimmed-down civil case: pleadings, discovery, "
             "evidence, briefs. Most oppositions settle or are withdrawn, but "
             "the ones that go the distance take a year or more.</li>\n</ol>\n")

    p.append("<h2>What it costs (TTAB fees, electronic filing)</h2>\n")
    p.append("<table class=\"f\"><thead><tr><th>Filing</th><th>Fee</th></tr></thead><tbody>\n")
    rows = [
        ("Notice of opposition, per class", usd(fs["opposition_per_class_electronic"])),
        ("Same, filed on paper", usd(fs["opposition_per_class_paper"])),
        ("Petition to cancel an existing registration, per class", usd(fs["cancellation_per_class_electronic"])),
        ("Extension of time to oppose — first 30 days", usd(fs["ext_first_30_days"])),
        ("Extension — 90 days from the original deadline (or a second 60 days)", usd(fs["ext_90_days_or_second_60"])),
        ("Extension — final 60 days", usd(fs["ext_final_60_days"])),
    ]
    for k, v in rows:
        p.append("<tr><td>%s</td><td>%s</td></tr>\n" % (e(k), e(v)))
    p.append("</tbody></table>\n")
    p.append("<p class=\"note\">Source: <a href=\"%s\" rel=\"noopener\">USPTO fee "
             "schedule</a>, effective %s, read by us on %s.%s Attorney fees are on "
             "top of these and are usually the larger number.</p>\n"
             % (e(fs["source_url"]), e(fs["effective"]), e(fs["verified_on"]), fee_stale))

    p.append("<h2>Why the window is the whole point of a trademark watch</h2>\n")
    p.append(
        "<p>Opposing a published application is the cheap moment. After it "
        "registers, the same objection becomes a petition to cancel — same fee "
        "per class, but now you are arguing against a presumptively valid "
        "registration, and every month it sits there the other side is building "
        "rights by use. The problem is that the %d days start on a date you were "
        "never told about. A watch is just someone (or something) reading every "
        "Tuesday's issue against your mark so the clock never runs out unnoticed.</p>\n" % days)
    p.append(
        "<p>You can do this by hand: the Gazette is public, and this site's "
        "<a href=\"filings/\">newly published marks by class</a> pages list every "
        "word mark from each issue. Doing it every week for years is the part "
        "people stop doing.</p>\n")

    p.append("<h2>Check right now, free</h2>\n")
    p.append(
        "<p>Type your mark into the <a href=\"./\">instant similarity check</a> — "
        "it runs in your browser against %s word marks from the Official Gazette "
        "back to %s (applications published for opposition and registrations "
        "issued) with edit-distance, phonetic and shared-rare-word matching. "
        "Every hit links to the mark's live USPTO status page, where the "
        "publication date and therefore the opposition deadline are shown.</p>\n"
        % (e("{:,}".format(corpus_total)), e(corpus_base)))

    p.append("<div class=\"cta\"><b>Have every future issue checked for you.</b>"
             "<p class=\"note\" style=\"margin:.4em 0 0\">Free for 30 days, no card: one "
             "mark, a private alert page and RSS feed, updated after each Tuesday "
             "issue. %s for a year if you want to keep it. Informational alerts, "
             "not legal opinions.</p>"
             "<a class=\"btn\" href=\"%s\">Watch my mark free for 30 days</a>"
             "<a class=\"btn2\" href=\"%s\">%s — one payment</a></div>\n"
             % (PRICE, e(FREE), e(BUY), PRICE_YR))

    p.append("<h2>If YOUR application is the one being opposed</h2>\n")
    p.append(
        "<p>You will get a notice from the TTAB with an answer deadline. Do not "
        "ignore it — a default ends the application. This is the point where "
        "talking to a trademark attorney stops being optional; the "
        "<a href=\"compare.html\">services we compare</a> include two that come "
        "with a lawyer on the other end, and we say plainly when they are the "
        "better buy.</p>\n")

    p.append("<footer><p><b>Not legal advice.</b> This page describes public USPTO "
             "procedure and quotes public fees; it is not an opinion about any "
             "specific mark, deadline or dispute. Fees and rules change: if a "
             "number here is out of date, <a href=\"%s/issues/new\">open an issue</a> "
             "and the page is regenerated on the next run. TM Watch is published by "
             "APProjects and sold through Gumroad (seller <i>approj</i>).</p></footer>\n"
             % e(REPO))
    p.append("</main>\n</body>\n</html>\n")
    return "".join(p), warns


def build_diy_watch(facts, data_date, stats, corpus_total, corpus_base):
    """The 'do I really need to pay for this?' page. Every number below is
    measured from OUR OWN published issue files (site/data/), so the page can
    never quote a figure the dataset does not support."""
    warns = []
    gz = facts["gazette"]
    pd_ = facts["period"]
    gz_stale = _stale(gz, data_date, warns, "gazette cadence")
    per_stale = _stale(pd_, data_date, warns, "opposition period")
    days = pd_["opposition_days"]
    n_iss = stats["issues"]
    latest = stats["latest"]
    first = stats["first"]
    lat_pub = stats["latest_published"]
    mean_rows = stats["mean_rows"]
    top = stats["top_classes"]
    big_c, big_n, big_name = top[0]
    # plain arithmetic, stated as arithmetic — one name per second, no breaks
    mins = int(round(big_n / 60.0))
    hrs_year = round(big_n * 52 / 3600.0, 1)

    p = []
    p.append("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n")
    p.append("<title>Watching your own trademark for free: the weekly routine, "
             "and when a paid watch is worth it | TM Watch</title>\n")
    p.append("<meta name=\"description\" content=\"How to run a trademark watch "
             "yourself, step by step, using free public Gazette data — plus the "
             "measured volume you are up against (%s newly published applications "
             "in the %s issue) and an honest account of where the DIY routine "
             "breaks down.\">\n" % ("{:,}".format(lat_pub), latest))
    p.append("<link rel=\"canonical\" href=\"%s/diy-trademark-watch.html\">\n" % BASE)
    p.append("<style>%s</style>\n</head>\n<body>\n<main>\n" % CSS)
    p.append("<p class=\"note\"><a href=\"./\">&larr; TM Watch — free instant similarity check</a></p>\n")
    p.append("<h1>You can watch your own trademark for free. Here is exactly how — "
             "and what it costs you in time.</h1>\n")
    p.append(
        "<p class=\"sub\">Trademark watching is not secret knowledge and it is not "
        "a licensed activity. The data is public, the routine is mechanical, and "
        "everything you need to run it is on this site at no charge. What follows "
        "is the honest version: the weekly steps, the volume you are actually "
        "reading, the part that quietly gets skipped, and the point where paying "
        "someone %s a year starts to make sense. We sell a watch, so read this "
        "with that in mind — which is also why every number here is measured from "
        "the same public files you can download.</p>\n" % PRICE)

    p.append("<h2>The routine, %s</h2>\n<ol class=\"steps\">\n" % (e(gz["cadence"]) + gz_stale))
    p.append("<li><b>Open that week's issue.</b> The USPTO publishes the "
             "<i>Trademark Official Gazette</i> %s. Every mark approved for "
             "publication that week appears in it, and the %d-day opposition "
             "clock for each of those marks starts on that date.%s</li>\n"
             % (e(gz["cadence"]), days, per_stale))
    p.append("<li><b>Cut it down to your classes.</b> Nobody reads the whole "
             "issue. Our <a href=\"filings/\">newly published marks by class</a> "
             "pages do this split for you — 45 pages, rebuilt after every issue, "
             "no login — and the per-issue CSVs on the <a href=\"data/\">data "
             "page</a> are the same rows if you would rather grep them.</li>\n")
    p.append("<li><b>Read for confusion, not for spelling.</b> A §2(d) refusal "
             "turns on sound, appearance, meaning and commercial impression, so "
             "the hits that matter are usually <i>not</i> exact matches of your "
             "name. This is the step that needs judgement and the step a plain "
             "Ctrl-F cannot do.</li>\n")
    p.append("<li><b>Check anything that worries you on TSDR.</b> Every mark on "
             "our pages links straight to its live USPTO status record, where the "
             "publication date, owner and goods description are authoritative.</li>\n")
    p.append("<li><b>Diary the deadline.</b> If you might oppose, the date to "
             "protect is %d days from that publication date — see "
             "<a href=\"opposition-window.html\">what happens in the opposition "
             "window</a> for the extension ladder and the fees.</li>\n"
             "<li><b>Do it again next week. Forever.</b></li>\n</ol>\n" % days)

    p.append("<h2>What you are actually reading, measured</h2>\n")
    p.append("<table class=\"f\"><thead><tr><th>Measured from our published issue "
             "files</th><th>Number</th></tr></thead><tbody>\n")
    rows = [
        ("Word marks in an average weekly issue (mean of %d issues, %s to %s)"
         % (n_iss, first, latest), "{:,}".format(mean_rows)),
        ("Newly published applications in the %s issue — the ones whose opposition "
         "clock just started" % latest, "{:,}".format(lat_pub)),
        ("Of those, in class %s (%s), the single busiest class that week"
         % (big_c, big_name), "{:,}".format(big_n)),
        ("Word marks in the searchable corpus behind this site (issues from %s)"
         % corpus_base, "{:,}".format(corpus_total)),
    ]
    for k, v in rows:
        p.append("<tr><td>%s</td><td>%s</td></tr>\n" % (e(k), e(v)))
    p.append("</tbody></table>\n")
    p.append("<p class=\"note\">These are counts of the rows we publish, not "
             "estimates: the per-issue CSVs are on the <a href=\"data/\">data "
             "page</a> and you can recount them yourself. Data through %s.</p>\n"
             % e(data_date))
    p.append(
        "<p>Suppose you are diligent and you narrow to that one busiest class. "
        "Reading %s names at one per second, without pausing to think about any "
        "of them, is about %d minutes — and that is the arithmetic, not a study. "
        "Fifty-two weeks of it is roughly %s hours a year of skimming in which "
        "the only acceptable error rate is zero, because the thing you are "
        "looking for shows up perhaps once.</p>\n"
        % (e("{:,}".format(big_n)), mins, e("%.1f" % hrs_year)))

    p.append("<h2>Where the DIY routine actually breaks</h2>\n")
    p.append("<p>Not on week one. Week one is fine — you are motivated, you just "
             "filed. It breaks in these three places:</p>\n<ol class=\"steps\">\n")
    p.append("<li><b>Attention decay.</b> The routine has no feedback: doing it "
             "perfectly and doing it not at all look identical for years, right "
             "up until the week they don't.</li>\n")
    p.append("<li><b>Near-misses.</b> Eyes match spellings; the Board matches "
             "impressions. Phonetic equivalents, one-letter drops, a shared rare "
             "word inside a longer name — all of those are ordinary §2(d) "
             "grounds and all of them survive a skim.</li>\n")
    p.append("<li><b>Scope creep.</b> The relevant class list is rarely just "
             "yours; related goods and services count too, and each class you "
             "add is another few thousand names a week.</li>\n</ol>\n")

    p.append("<h2>The free way to do it better</h2>\n")
    p.append(
        "<p>Before you pay anyone — us included — use the free surfaces here. "
        "The <a href=\"./\">instant similarity check</a> runs the same matcher "
        "our paid watch uses, in your browser, against all %s marks: edit "
        "distance, phonetic codes and shared-rare-word overlap, with every hit "
        "linked to TSDR. Run it on your mark today, run it again after each "
        "Tuesday issue, and you have most of a watch for nothing. The "
        "<a href=\"data/\">per-issue CSVs</a> and the "
        "<a href=\"https://github.com/APVentureEngine/trademark-watch\" "
        "rel=\"noopener\">source code</a> are public too; if you would rather "
        "run the whole thing on your own machine, it is all there.</p>\n"
        % e("{:,}".format(corpus_total)))

    p.append("<h2>What paying changes</h2>\n")
    p.append(
        "<p>Exactly one thing: it happens whether or not you remember. After "
        "each issue we run your mark through the matcher, write the hits to a "
        "private alert page and an RSS feed, and keep doing that for the term "
        "you bought. No dashboard to log into, no card on file, no "
        "auto-renewal. Email alerts are <i>not</i> built yet and we say so on "
        "every page until they are.</p>\n")
    p.append(
        "<p>Honest limits: we watch <b>word marks</b> from the US Gazette, not "
        "design marks, not international registers, and we do not give legal "
        "opinions or file anything for you. If you need those, the "
        "<a href=\"compare.html\">comparison page</a> lists the paid services "
        "that do, with dated prices — including the ones that beat us.</p>\n")

    p.append("<div class=\"cta\"><b>Try the paid routine without paying.</b>"
             "<p class=\"note\" style=\"margin:.4em 0 0\">Free for 30 days, no card: "
             "one mark, checked after every issue, private alert page plus RSS. "
             "%s for a year if it earns its keep. Informational alerts, not "
             "legal opinions.</p>"
             "<a class=\"btn\" href=\"%s\">Watch my mark free for 30 days</a>"
             "<a class=\"btn2\" href=\"%s\">%s — one payment</a></div>\n"
             % (PRICE, e(FREE), e(BUY), PRICE_YR))

    p.append("<footer><p><b>Not legal advice.</b> This page describes public USPTO "
             "procedure and counts of public records; it is not an opinion about "
             "any specific mark, deadline or dispute. If a number here looks "
             "wrong, <a href=\"%s/issues/new\">open an issue</a> — the page is "
             "regenerated from the data on every run. TM Watch is published by "
             "APProjects and sold through Gumroad (seller <i>approj</i>).</p></footer>\n"
             % e(REPO))
    p.append("</main>\n</body>\n</html>\n")
    return "".join(p), warns


def load_competitors(path=None):
    with open(path or os.path.join(HERE, "competitors.json")) as f:
        return json.load(f)["competitors"]


def build_watch_cost(facts, data_date, competitors, corpus_total, corpus_base):
    """The price-intent page: 'how much does a trademark watch cost'. The
    compare page is a table; this is the prose answer. EVERY dollar figure
    comes from competitors.json (with its verified_on date) or FACTS, so the
    page cannot quote a price nobody fetched. Rows older than STALE_DAYS get
    the red marker and a WARN, exactly like gen_compare."""
    warns = []
    fee = facts["fee_schedule"]
    pd_ = facts["period"]
    fee_stale = _stale(fee, data_date, warns, "fee schedule")
    per_stale = _stale(pd_, data_date, warns, "opposition period")
    paid = [c for c in competitors if c["price_usd_year"] > 0]
    paid = sorted(paid, key=lambda c: (c["price_usd_year"], c["name"]))
    free = [c for c in competitors if c["price_usd_year"] == 0]
    cheapest, dearest = paid[0], paid[-1]
    # a multi-mark bundle is the one price shape a per-mark comparison misreads
    bundles = [c for c in paid if re.search(r"\bmarks\b", c["price_label"])]
    bundle = bundles[0] if bundles else None
    be_marks = (bundle_break_even(bundle["price_usd_year"], cheapest["price_usd_year"])
                if bundle else None)
    lo = min(PRICE_USD, cheapest["price_usd_year"])   # the floor of the range INCLUDES our price
    cheaper = cheaper_competitors(competitors)         # computed, never asserted by hand
    stale_of = {}
    for c in competitors:
        s = _days_between(c["verified_on"], data_date) > STALE_DAYS
        stale_of[c["name"]] = s
        if s:
            warns.append("STALE: %s price verified %s, data date %s (>%dd)"
                         % (c["name"], c["verified_on"], data_date, STALE_DAYS))

    def mark(name):
        return (" <span class=\"stale\">(needs re-checking)</span>"
                if stale_of.get(name) else "")

    def price_line(c):
        return ("<a href=\"%s\" rel=\"noopener nofollow\">%s</a>: %s "
                "<span class=\"note\">(read %s)</span>%s"
                % (e(c["source_url"]), e(c["name"]), e(c["price_label"]),
                   e(c["verified_on"]), mark(c["name"])))

    opp = fee["opposition_per_class_electronic"]
    days = pd_["opposition_days"]

    p = []
    p.append("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n")
    p.append("<title>How much does a trademark watch cost? Real prices, read on "
             "a stated date | TM Watch</title>\n")
    p.append("<meta name=\"description\" content=\"Trademark watch pricing in "
             "plain numbers: from free (do it yourself) to %s a year per mark, "
             "what makes the price move, and the one cost that dwarfs all of "
             "them. Every figure links to the page it was read from, with the "
             "date.\">\n" % e(usd(lo)))
    p.append("<link rel=\"canonical\" href=\"%s/trademark-watch-cost.html\">\n" % BASE)
    p.append("<style>%s</style>\n</head>\n<body>\n<main>\n" % CSS)
    p.append("<p class=\"note\"><a href=\"./\">&larr; TM Watch — free instant similarity check</a></p>\n")
    p.append("<h1>How much does a trademark watch cost?</h1>\n")
    p.append(
        "<p class=\"sub\">Short answer, for one US word mark: <b>nothing</b> if you "
        "run the weekly check yourself, <b>%s to %s a year</b> for the "
        "self-serve services whose prices are published (this site included), and a quote you have "
        "to ask for if you want a law firm or an enterprise vendor to do it. "
        "Every number below was read off the seller's own page on the date "
        "shown; when a figure is more than %d days old this page marks it "
        "in red rather than pretending it is still true.</p>\n"
        % (e(usd(lo)), e(usd(dearest["price_usd_year"])),
           STALE_DAYS))

    p.append("<h2>The published prices, cheapest first</h2>\n")
    p.append("<ul>\n")
    for c in free:
        p.append("<li>%s — %s</li>\n" % (price_line(c), e(c["delivery"])))
    for c in paid:
        p.append("<li>%s — %s</li>\n" % (price_line(c), e(c["delivery"])))
    p.append("<li><a href=\"./\">TM Watch</a> (this site): <b>%s for one year</b>, one "
             "mark, one payment, no auto-renewal; the first 30 days are free "
             "with no card. Word marks from the US Trademark Official Gazette "
             "only — hits go to a private alert page and an RSS feed.</li>\n" % PRICE)
    p.append("</ul>\n")
    p.append("<p>Two things are worth saying out loud. ")
    if cheaper:
        p.append("%s is cheaper than we are for a single US mark. " % e(cheaper[0]["name"]))
    else:
        p.append("At %s a year we are the lowest per-mark price on this page as of the "
                 "dates shown (%s is next at %s), and the prices are re-read on every "
                 "rebuild, so if that stops being true this sentence changes. "
                 % (PRICE, e(cheapest["name"]), e(usd(cheapest["price_usd_year"]))))
    if bundle:
        p.append("%s prices per bundle, not per mark, so from mark %d onward it "
                 "is cheaper than any per-mark service on this page, us "
                 "included. " % (e(bundle["name"]), be_marks))
    p.append("The <a href=\"compare.html\">comparison table</a> shows the same "
             "rows with coverage and delivery side by side, including the "
             "columns where each of them beats us.</p>\n")

    p.append("<h2>What actually moves the price</h2>\n")
    p.append("<ol class=\"steps\">\n")
    p.append("<li><b>How many marks.</b> Almost everyone prices per mark. A "
             "service that bundles several marks for one fee%s wins for a "
             "portfolio and loses for a single name.</li>\n"
             % ((" (%s does)" % e(bundle["name"])) if bundle else ""))
    p.append("<li><b>How many registers.</b> US only is the floor. The vendors "
             "above that cover foreign registers (EU, UK, WIPO, &ldquo;global&rdquo;) "
             "sell them as separate, higher tiers; %s, for example, lists EU and global "
             "prices well above its US figure. We quote only the US price here "
             "and only watch the US Gazette.</li>\n" % e(cheapest["name"]))
    p.append("<li><b>Who reads the hits.</b> An algorithm (us, and most of the "
             "cheap tier) sends you every plausible match and leaves the "
             "judgement to you. A human analyst or an attorney filters first "
             "and, at the top of the range, will get on the phone about a "
             "conflict. That is what the higher figures buy.</li>\n")
    p.append("<li><b>Word marks vs. designs.</b> Logo and design-mark watching "
             "needs image comparison and, where it is offered, is a separate "
             "product. We do not offer it at all.</li>\n")
    p.append("<li><b>Delivery.</b> Weekly email reports are the norm. We are "
             "honest that email alerts are <i>not</i> built yet — you get a "
             "private page and an RSS feed — and that is part of why we are "
             "cheap.</li>\n")
    p.append("</ol>\n")

    p.append("<h2>The cost that makes the watch fee irrelevant</h2>\n")
    p.append(
        "<p>A watch exists to catch a conflicting application while it is still "
        "cheap to act on. Once an application is published, you have "
        "<b>%d days</b>%s to oppose it; the USPTO's filing fee for a notice "
        "of opposition is <b>%s per class</b> (electronic filing)%s, before "
        "any attorney time. Miss the window and the application moves on "
        "toward registration; undoing a registration later means a "
        "cancellation proceeding at %s per class%s, from a weaker position. "
        "The <a href=\"opposition-window.html\">"
        "opposition-window page</a> walks through the deadlines and the "
        "extension fees. Against those numbers, the difference between a %s "
        "watch and a %s watch is noise; the difference between watching and "
        "not watching is not.</p>\n"
        % (days, per_stale, e(usd(opp)), fee_stale,
           e(usd(fee["cancellation_per_class_electronic"])), fee_stale,
           e(usd(lo)), e(usd(dearest["price_usd_year"]))))

    p.append("<h2>When the right price is zero</h2>\n")
    p.append(
        "<p>If you will genuinely check every Tuesday, you do not need to pay "
        "anyone. The <a href=\"diy-trademark-watch.html\">DIY page</a> gives "
        "the exact routine, and the <a href=\"./\">instant similarity check</a> "
        "runs the same matcher our paid watch uses, in your browser, against "
        "all %s word marks published since %s. Paying for a watch buys one "
        "thing: it happens whether or not you remember.</p>\n"
        % (e("{:,}".format(corpus_total)), e(corpus_base)))

    p.append("<div class=\"cta\"><b>Find out what a watch costs you: nothing, for 30 days.</b>"
             "<p class=\"note\" style=\"margin:.4em 0 0\">One mark, checked after "
             "every Gazette issue, private alert page plus RSS. No card. %s for "
             "a year if it earns its keep. Informational alerts, not legal "
             "opinions.</p>"
             "<a class=\"btn\" href=\"%s\">Watch my mark free for 30 days</a>"
             "<a class=\"btn2\" href=\"%s\">%s — one payment</a></div>\n"
             % (PRICE, e(FREE), e(BUY), PRICE_YR))

    p.append("<footer><p><b>Not legal advice.</b> Competitor prices are quoted as "
             "read on the dates shown and may have changed; the link on each "
             "name goes to the page we read. USPTO fees are from the schedule "
             "effective %s, read %s. If a number here is wrong, "
             "<a href=\"%s/issues/new\">open an issue</a> — the page is "
             "regenerated from the data on every run. TM Watch is published by "
             "APProjects and sold through Gumroad (seller <i>approj</i>).</p></footer>\n"
             % (e(fee["effective"]), e(fee["verified_on"]), e(REPO)))
    p.append("</main>\n</body>\n</html>\n")
    return "".join(p), warns


def load_issue_stats(site_dir):
    """Measured facts about the published issue files (site/data/), so the DIY
    page quotes only numbers our own dataset supports."""
    import csv as _csv
    try:
        from gen_seo import CLASS_NAMES
    except Exception:
        CLASS_NAMES = {}
    with open(os.path.join(site_dir, "data", "manifest.json")) as f:
        man = json.load(f)
    issues = man["issues"]
    keys = sorted(issues)
    latest = keys[-1]
    mean_rows = int(round(sum(i["rows"] for i in issues.values()) / float(len(issues))))
    pub = 0
    per_class = {}
    with open(os.path.join(site_dir, "data", issues[latest]["csv"].replace("/", os.sep))) as f:
        for row in _csv.DictReader(f):
            if (row.get("event") or "").strip() == "published":
                pub += 1
                for c in (row.get("classes") or "").replace(";", " ").split():
                    if c.isdigit():
                        per_class[int(c)] = per_class.get(int(c), 0) + 1
    top = sorted(per_class.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return {
        "issues": len(keys), "first": keys[0], "latest": latest,
        "latest_rows": issues[latest]["rows"], "latest_published": pub,
        "mean_rows": mean_rows,
        "top_classes": [(c, n, CLASS_NAMES.get(c, "class %d" % c)) for c, n in top],
    }


SAMPLE_STATS = {
    "issues": 18, "first": "2026-05-05", "latest": "2026-09-01",
    "latest_rows": 20233, "latest_published": 10401, "mean_rows": 20070,
    "top_classes": [(9, 1345, "Computers & electronics"), (41, 1301, "Education & entertainment"),
                    (35, 1150, "Advertising & business")],
}


def load_manifest(site_dir):
    with open(os.path.join(site_dir, "index", "manifest.json")) as f:
        m = json.load(f)
    return m["generated"], int(m["total"]), m["base"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "site"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    data_date, total, base = load_manifest(a.out)
    stats = load_issue_stats(a.out)
    pages = [
        ("opposition-window.html", build_opposition_window(FACTS, data_date, total, base)),
        ("diy-trademark-watch.html", build_diy_watch(FACTS, data_date, stats, total, base)),
        ("trademark-watch-cost.html", build_watch_cost(FACTS, data_date, load_competitors(), total, base)),
    ]
    for name, (text, warns) in pages:
        dest = os.path.join(a.out, name)
        with open(dest, "w") as f:
            f.write(text)
        for w in warns:
            print("gen_guides: WARN %s" % w)
        print("gen_guides: -> %s (%d bytes, data %s)" % (dest, len(text), data_date))
    return 0


def selftest():
    t1, w1 = build_opposition_window(FACTS, "2026-09-03", 361260, "2026-05-05")
    t2, _ = build_opposition_window(FACTS, "2026-09-03", 361260, "2026-05-05")
    assert t1 == t2, "not deterministic"
    assert not w1, w1
    assert "needs re-checking" not in t1
    # every fee must appear, formatted, and the source + verified date shown
    for s in ("$600", "$700", "$200", "$400", "$0 (no fee)", "2025-01-19", "2026-09-03"):
        assert s in t1, s
    assert "361,260" in t1 and "2026-05-05" in t1
    assert "Not legal advice" in t1 and FREE in t1 and BUY in t1
    assert "%s" not in t1 and "%d" not in t1 and "TODO" not in t1
    # staleness: a data date 91+ days after verification must flag + warn
    t3, w3 = build_opposition_window(FACTS, "2026-12-15", 361260, "2026-05-05")
    assert "needs re-checking" in t3 and len(w3) == 2, w3

    # --- DIY guide (c99) -------------------------------------------------
    d1, dw1 = build_diy_watch(FACTS, "2026-09-03", SAMPLE_STATS, 361260, "2026-05-05")
    d2, _ = build_diy_watch(FACTS, "2026-09-03", SAMPLE_STATS, 361260, "2026-05-05")
    assert d1 == d2, "diy not deterministic"
    assert not dw1, dw1
    assert "needs re-checking" not in d1
    # every measured number must be rendered, formatted, and none invented
    for s in ("10,401", "20,070", "1,345", "361,260", "2026-05-05", "2026-09-01",
              "Computers &amp; electronics", "18 issues"):
        assert s in d1, s
    assert PRICE in d1 and OLD_PRICE not in d1 and FREE in d1 and BUY in d1
    assert "Not legal advice" in d1 and "Email alerts are <i>not</i> built yet" in d1
    assert "%s" not in d1 and "%d" not in d1 and "TODO" not in d1
    # arithmetic actually derived from the stats, not hard-coded
    assert " %d minutes" % int(round(1345 / 60.0)) in d1
    d3, dw3 = build_diy_watch(FACTS, "2026-12-15", SAMPLE_STATS, 361260, "2026-05-05")
    assert "needs re-checking" in d3 and len(dw3) == 2, dw3
    # --- cost page (c100) -------------------------------------------------
    SAMPLE_COMP = [
        {"name": "Alpha Watch", "price_label": "$39/yr per mark", "price_usd_year": 39,
         "delivery": "Weekly email", "source_url": "https://alpha.test/p", "verified_on": "2026-09-01"},
        {"name": "Bundle Law", "price_label": "$99/yr for up to 5 marks", "price_usd_year": 99,
         "delivery": "Email + call", "source_url": "https://bundle.test/p", "verified_on": "2026-09-01"},
        {"name": "Free search", "price_label": "Free", "price_usd_year": 0,
         "delivery": "You search", "source_url": "https://free.test/", "verified_on": "2026-09-01"},
    ]
    c1, cw1 = build_watch_cost(FACTS, "2026-09-03", SAMPLE_COMP, 361260, "2026-05-05")
    c2, _ = build_watch_cost(FACTS, "2026-09-03", SAMPLE_COMP, 361260, "2026-05-05")
    assert c1 == c2, "cost page not deterministic"
    assert not cw1, cw1
    assert "needs re-checking" not in c1
    for s in ("$39", "$99", "$600", "30 days", "361,260", "2026-05-05", "Alpha Watch",
              "Bundle Law", "Free search", "read 2026-09-01", "from mark 4 onward",
              "$29 to $99 a year", "$29 for one year", "alpha.test/p",
              "lowest per-mark price", "Alpha Watch is next at $39"):
        assert s in c1, s
    assert c1.index("Free search") < c1.index("Alpha Watch") < c1.index("Bundle Law")
    assert "Not legal advice" not in c1[:200] and "Not legal advice" in c1
    assert FREE in c1 and BUY in c1 and "not</i> built yet" in c1
    assert "%s" not in c1 and "%d" not in c1 and "TODO" not in c1
    # stale competitor row -> red marker + WARN; stale FACTS -> two more WARNs
    c3, cw3 = build_watch_cost(FACTS, "2026-12-15", SAMPLE_COMP, 361260, "2026-05-05")
    assert c3.count("needs re-checking") == 6 and len(cw3) == 5, (c3.count("needs re-checking"), cw3)
    # no bundle row -> the bundle sentence is simply absent, never a crash
    c4, _ = build_watch_cost(FACTS, "2026-09-03", SAMPLE_COMP[:1] + SAMPLE_COMP[2:], 361260, "2026-05-05")
    assert "onward" not in c4 and "$29 to $39 a year" in c4
    # a competitor priced BELOW us flips the sentence to the concession, computed not typed
    cheap = [dict(SAMPLE_COMP[0], name="Budget Watch", price_label="$19/yr per mark", price_usd_year=19)] + SAMPLE_COMP
    c6, _ = build_watch_cost(FACTS, "2026-09-03", cheap, 361260, "2026-05-05")
    assert "Budget Watch is cheaper than we are" in c6 and "lowest per-mark price" not in c6
    assert "$19 to $99 a year" in c6 and "from mark 6 onward" in c6, "break-even must use the true floor"
    assert OLD_PRICE not in c1 and OLD_PRICE not in c6
    # the LIVE competitors.json must also render clean today
    c5, cw5 = build_watch_cost(FACTS, "2026-09-03", load_competitors(), 361260, "2026-05-05")
    assert "Markify" in c5 and "Hawthorn Law" in c5 and (PRICE + " for one year") in c5, "live competitors"
    print("gen_guides selftest: OK (%d + %d + %d bytes)" % (len(t1), len(d1), len(c1)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
