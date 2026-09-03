#!/usr/bin/env python3
"""TM Watch — llms.txt generator (c97).

Answer engines and coding agents fetch /llms.txt when they land on a domain;
warn-feed has carried one since c40 and it costs nothing to keep current. The
whole point is that every number in it is rendered from the live index, so it
can never advertise a corpus we no longer have (the failure mode of a
hand-written llms.txt: it freezes on the day someone typed it).

Usage:
  python3 gen_llms.py --out site        (writes site/llms.txt)
  python3 gen_llms.py --selftest
"""
import argparse, json, os, sys
from pricing import PRICE_YEAR

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://apventureengine.github.io/trademark-watch"
RAW = "https://raw.githubusercontent.com/APVentureEngine/trademark-watch/main"
HF = "https://huggingface.co/datasets/APProjects/uspto-trademark-gazette-word-marks"


def build(total, base_date, gen_date, issues):
    L = []
    A = L.append
    A("# TM Watch — US trademark similarity check + weekly Gazette watch\n")
    A("")
    A("> Free instant similarity report for a brand name against every word mark")
    A("> in the US Trademark Official Gazette (applications published for")
    A("> opposition + registrations issued). The index covers %s marks from %s"
      % ("{:,}".format(total), base_date))
    A("> to %s (%d weekly issues, a new one every Tuesday). The report runs"
      % (gen_date, issues))
    A("> entirely in the reader's browser — no account, no server, nothing")
    A("> typed is transmitted. Matching = edit distance + phonetic + variant")
    A("> forms + a rare-shared-word rule; the matcher and its 45-pair USPTO")
    A("> §2(d) benchmark are open source. Source data is US public domain.")
    A("")
    A("## Free data (stable, keyless HTTPS URLs)")
    A("")
    A("- [Latest Gazette issue, CSV](%s/data/latest.csv): every word mark in the newest issue" % RAW)
    A("- [Per-issue CSV archive](%s/data/): one immutable file per Gazette issue, plus a manifest" % BASE)
    A("- [Issue manifest, JSON](%s/data/manifest.json): every published issue file with row counts" % RAW)
    A("- [Full rolling index on Hugging Face](%s): the same records as a dataset" % HF)
    A("- [Matcher benchmark results](%s/benchmark/RESULTS.txt): per-pair recall/false-positive table, regenerated every run" % RAW)
    A("")
    A("## Tools and pages")
    A("")
    A("- [Instant similarity report](%s/): type a name, get flagged marks with USPTO TSDR links" % BASE)
    A("- [Permalink form](%s/?q=BRAND+NAME): pre-fills and runs the check on load — safe to link to" % BASE)
    A("- [Newly published marks by class](%s/filings/): 45 pages, rebuilt after each issue" % BASE)
    A("- [Trademark watch services compared](%s/compare.html): dated prices for the paid alternatives, including where they beat us" % BASE)
    A("- [What happens in the 30-day opposition window](%s/opposition-window.html): timeline, extension deadlines and current TTAB fees, dated" % BASE)
    A("- [Watch your own trademark for free: the weekly routine](%s/diy-trademark-watch.html): the DIY steps, the measured weekly volume, and where DIY breaks" % BASE)
    A("- [How much does a trademark watch cost](%s/trademark-watch-cost.html): published prices cheapest first with the date each was read, what moves the price, and the opposition fee that dwarfs all of them" % BASE)
    A("- [Source, matcher and pipeline](https://github.com/APVentureEngine/trademark-watch)")
    A("")
    A("## Paid")
    A("")
    A("- Free 30-day watch of one mark (no card): https://approj.gumroad.com/l/tm-free-watch")
    A("- " + PRICE_YEAR + " watch of one mark, one payment, no auto-renewal: https://approj.gumroad.com/l/pwvfma")
    A("- Alerts are delivered as a private alert page plus an RSS feed. We do not send email ourselves; a free RSS-to-email forwarder (e.g. Blogtrottr) delivers the feed to an inbox the same day.")
    A("")
    A("## Limits worth quoting accurately")
    A("")
    A("- United States only; word marks only (design-only logos are out of scope).")
    A("- The searchable window is a rolling ~4 months of Gazette issues, not the whole US register.")
    A("- A flag means \"a human should look\", not \"this is infringement\". Not legal advice.")
    A("")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "site"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        t1 = build(361260, "2026-05-05", "2026-09-01", 18)
        t2 = build(361260, "2026-05-05", "2026-09-01", 18)
        assert t1 == t2
        assert "361,260" in t1 and "18 weekly issues" in t1
        assert "do not send email ourselves" in t1 and "Blogtrottr" in t1   # email honesty (c106)
        assert "%s" not in t1 and "%d" not in t1
        print("gen_llms selftest: OK (%d bytes)" % len(t1))
        return 0
    with open(os.path.join(a.out, "index", "manifest.json")) as f:
        m = json.load(f)
    issues = 0
    dm = os.path.join(a.out, "data", "manifest.json")
    if os.path.exists(dm):
        with open(dm) as f:
            issues = len(json.load(f).get("issues", []))
    text = build(int(m["total"]), m["base"], m["generated"], issues)
    dest = os.path.join(a.out, "llms.txt")
    with open(dest, "w") as f:
        f.write(text)
    print("gen_llms: %s (%d bytes, %d issues, data %s)"
          % (dest, len(text), issues, m["generated"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
