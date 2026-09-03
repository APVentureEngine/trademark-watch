"""TM Watch — the ONE place the paid price lives (c104, 2026-09-03).

Every generator (site pages, compare/cost pages, llms.txt, alert-page banners,
Gumroad receipts/PDF/cover, fulfil texts) imports from here. Never type a
dollar figure for our own product anywhere else: the c103 site review scored
differentiation 40/100 because the page conceded Markify ($39/yr) was cheaper
than our $49, and re-pricing touched 12 hand-typed surfaces. `python3
pricing.py --audit` greps the product tree for stray "$49"/"4900" literals and
is wired into publish.sh as a gate.

History: $49/yr (2026-09-01 launch) -> $29/yr (2026-09-03, c104), priced
below the cheapest published per-mark competitor in competitors.json.
"""
import os, re, sys

PRICE_USD = 29                      # one mark, twelve months, one payment
PRICE_CENTS = PRICE_USD * 100       # what Gumroad's API expects
PRICE = "$%d" % PRICE_USD           # "$29"
PRICE_YR = PRICE + "/yr"            # "$29/yr"
PRICE_YEAR = PRICE + "/year"        # "$29/year"
PRICE_PHRASE = PRICE + " for one mark, 12 months — one-time payment, no auto-renewal"
OLD_PRICE = "$" + "49"              # for negative assertions (kept out of the audit regex on purpose)
GUMROAD_PAID_ID = "yqoJ16p67-UfQ1hnOtExvQ=="
GUMROAD_FREE_ID = "DXbAI_1fRuKYAp8J7GUz0Q=="

# literals that must never reappear once the price moved
OLD_LITERALS = (r"\$49\b", r"\b4900\b", r"\b49/y(ea)?r\b", r"\$49 ?/ ?mark")


def cheaper_competitors(competitors):
    """Paid rows priced strictly below us per mark (single-mark price shapes only)."""
    return sorted((c for c in competitors
                   if 0 < c["price_usd_year"] < PRICE_USD
                   and not re.search(r"\bmarks\b", c["price_label"])),
                  key=lambda c: c["price_usd_year"])


def bundle_break_even(bundle_price, cheapest_per_mark):
    """First mark count at which a flat bundle beats the cheapest per-mark price,
    OUR price included."""
    per = min(cheapest_per_mark, PRICE_USD)
    return int(bundle_price // per) + 1


def audit(root=None):
    """Return [(path, lineno, line)] for stray old-price literals in shipped
    surfaces. Excludes data, venv, git, generated site/ (rebuilt anyway) and
    this file."""
    root = root or os.path.dirname(os.path.abspath(__file__))
    hits = []
    skip_dirs = {".venv", ".git", "__pycache__", "downloads", "hf_staging", "index", "alerts", "filings"}
    exts = (".py", ".html", ".sh", ".md", ".txt", ".js")
    pat = re.compile("|".join(OLD_LITERALS))
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in skip_dirs]
        for fn in fns:
            if not fn.endswith(exts) or fn in ("pricing.py", "pipeline.log", "log.md"):
                continue
            p = os.path.join(dp, fn)
            try:
                for i, line in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
                    if pat.search(line):
                        hits.append((os.path.relpath(p, root), i, line.strip()[:120]))
            except OSError:
                pass
    return hits


def check_index(root=None):
    """site/index.html is HAND-maintained: it must carry today's price phrase and
    quote competitor prices that match competitors.json (the note under the
    price names Markify + Hawthorn Law by number)."""
    import json
    root = root or os.path.dirname(os.path.abspath(__file__))
    s = open(os.path.join(root, "site", "index.html"), encoding="utf-8").read()
    problems = []
    if PRICE_PHRASE not in s:
        problems.append("index.html lacks the price phrase %r" % PRICE_PHRASE)
    comps = json.load(open(os.path.join(root, "competitors.json")))["competitors"]
    for c in comps:
        if c["price_usd_year"] > 0 and c["name"] in s:
            want = "$%d/yr" % c["price_usd_year"]
            if want not in s:
                problems.append("index.html names %s but not its price %s" % (c["name"], want))
    # c107: the alert-page address includes the checkout passphrase; the page a
    # buyer decides on must say so, or the finder form asks for something the
    # sales copy never mentioned.
    if "passphrase" not in s.lower():
        problems.append("index.html never mentions the checkout passphrase (alert-page address needs it)")
    cheaper = cheaper_competitors(comps)
    if cheaper and "Priced below every single-mark watch" in s:
        problems.append("index.html claims lowest price but %s is cheaper" % cheaper[0]["name"])
    return problems


def check_readme(root=None):
    """repo/README.md is HAND-maintained and is the artifact a stranger inspects
    to decide we are real. c108 found it still saying email was the primary
    delivery (retired c106) and alerts/<sha256(mark|email)> (passphrase added
    c107). Assert the current truths and ban the retired claims."""
    root = root or os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(root, "repo", "README.md")
    if not os.path.exists(p):
        return ["repo/README.md missing"]
    s = open(p, encoding="utf-8").read()
    problems = []
    for bad, why in (
        ("sha256(mark|email)>", "alert address omits the passphrase (c107)"),
        ("email (primary", "email is NOT a delivery route we run (c106)"),
        ("uspto-gazette-word-marks**", "old HF dataset id (renamed c91)"),
    ):
        if bad in s:
            problems.append("README says %r — %s" % (bad, why))
    for need in ("passphrase", "RSS-to-email", "not built yet", PRICE_YR):
        if need not in s:
            problems.append("README lacks %r" % need)
    return problems


def main():
    if "--audit" in sys.argv:
        hits = audit()
        for h in hits:
            print("STRAY PRICE %s:%d: %s" % h)
        probs = check_index()
        for p in probs:
            print("INDEX PRICE: " + p)
        rp = check_readme()
        for p in rp:
            print("README CLAIM: " + p)
        probs = probs + rp
        print("pricing audit: %d stray literal(s), %d index problem(s); price is %s"
              % (len(hits), len(probs), PRICE_YR))
        return 1 if (hits or probs) else 0
    print(PRICE_YR)
    return 0


if __name__ == "__main__":
    sys.exit(main())


# c106: delivery wording. We do NOT send email ourselves (no mail key; A014).
# What IS true today: every alert page has an RSS feed, and a free RSS-to-email
# forwarder turns that into an inbox alert the same day. Say exactly that —
# never "on the roadmap" — on every surface. Verified 2026-09-03: blogtrottr.com
# is live, free, offers "As soon as possible" delivery.
EMAIL_ROUTE_HTML = ('Want it in your inbox? We do not send email ourselves yet: paste your alert page\'s '
                    '<code>feed.xml</code> address into a free RSS-to-email forwarder such as '
                    '<a href="https://blogtrottr.com/" rel="nofollow">Blogtrottr</a> (choose "as soon as possible") '
                    'and each hit lands in your email the same day it reaches the page. Takes about a minute, no account with us.')
EMAIL_ROUTE_TEXT = ("Want it in your inbox? We do not send email ourselves yet: paste the page's feed.xml address into a "
                    "free RSS-to-email forwarder such as Blogtrottr (blogtrottr.com, choose 'as soon as possible') and each "
                    "hit lands in your email the same day it reaches the page.")
