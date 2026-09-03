#!/usr/bin/env python3
"""Gumroad cover (1280x720 PNG) + one-page 'how your watch works' PDF for TM Watch.

Run with an interpreter that has Pillow (warn-feed's .venv has 12.x; no system
TTF fonts on the VM -> ImageFont.load_default(size=)). Content is a REAL alert
row set (Stellanite vs the 2026-09-01 Gazette), not lorem ipsum.
Outputs: ../assets/cover.png, ../assets/how-your-watch-works.pdf
"""
import os
from PIL import Image, ImageDraw, ImageFont
from pricing import PRICE

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "assets")
os.makedirs(OUT, exist_ok=True)

INK, MUT, ACC, SOFT, WARN = (26, 26, 36), (102, 102, 102), (11, 95, 255), (244, 246, 250), (176, 0, 32)
ROWS = [
    ("Serial", "Mark", "Gazette date", "Event", "Cls", "Why flagged"),
    ("50001495", "STELLANITE", "2026-09-01", "Published for opposition", "11", "identical, phonetic-equal STLNT"),
    ("50001643", "STEELANITE", "2026-09-01", "Published for opposition", "11", "edit sim 0.90, phonetic-equal"),
    ("98152938", "STELLA ARTE", "2026-07-21", "Registered", "3", "edit sim 0.80, phonetic-near"),
]


def F(sz):
    return ImageFont.load_default(size=sz)


def table(d, x, y, rows, widths, fs=22, rowh=40):
    for i, r in enumerate(rows):
        cx = x
        if i == 0:
            d.rectangle([x, y, x + sum(widths), y + rowh], fill=SOFT)
        else:
            d.line([x, y + rowh, x + sum(widths), y + rowh], fill=(223, 229, 240), width=1)
        for cell, w in zip(r, widths):
            d.text((cx + 10, y + (rowh - fs) // 2), cell, fill=INK if i else MUT, font=F(fs))
            cx += w
        y += rowh
    return y


def bench_line():
    """Render the benchmark claim FROM benchmark-results.txt (c101). It was
    hand-typed ("24 pairs: 20/20") and had gone stale against the real file
    (36 must-flag pairs, 0/20 false positives) — a false claim on the cover
    image that a buyer sees before anything else."""
    import re
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark-results.txt")
    rec = fp = None
    with open(path) as fh:
        for ln in fh:
            m = re.search(r"RECALL \(must-flag\):\s*(\d+)/(\d+)", ln)
            if m:
                rec = (int(m.group(1)), int(m.group(2)))
            m = re.search(r"NEGATIVE-CONTROL false positives:\s*(\d+)/(\d+)", ln)
            if m:
                fp = (int(m.group(1)), int(m.group(2)))
    if not rec or not fp:
        raise SystemExit("benchmark-results.txt: could not read RECALL / NEGATIVE-CONTROL lines")
    return ("Open-source edit-distance + phonetic matcher, benchmarked on real §2(d) pairs: "
            f"{rec[0]}/{rec[1]} caught, {fp[0]}/{fp[1]} false positives on negative controls.")


def cover(free=False):
    im = Image.new("RGB", (1280, 720), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1280, 12], fill=ACC)
    d.text((60, 48), "TM Watch", fill=ACC, font=F(34))
    d.text((60, 96), "You hear on day 0 of the 30-day opposition window.", fill=INK, font=F(46))
    d.text((60, 158),
           "Every Tuesday's USPTO Official Gazette matched against your mark. Free for 30 days, no card."
           if free else
           "Every Tuesday's USPTO Official Gazette matched against your mark. %s / mark / year." % PRICE,
           fill=MUT, font=F(26))
    d.text((60, 218), "Real alert — watched mark STELLANITE, issue 2026-09-01:", fill=INK, font=F(24))
    d.rectangle([60, 256, 1220, 256 + 40 * len(ROWS) + 4], outline=(223, 229, 240), width=2)
    table(d, 62, 258, ROWS, [130, 190, 170, 300, 70, 300], fs=21, rowh=40)
    y = 256 + 40 * len(ROWS) + 40
    for line in (bench_line(),
                 "Alerts land on your own private alert page + RSS feed — no account needed. "
                 "One-time payment, 12 months, 14-day refund."):
        d.text((60, y), line, fill=MUT, font=F(22)); y += 34
    d.rectangle([60, 640, 1220, 690], fill=ACC)
    d.text((80, 652),
           "Free instant similarity check: apventureengine.github.io/trademark-watch"
           if free else
           "Try it free first: apventureengine.github.io/trademark-watch",
           fill="white", font=F(26))
    p = os.path.join(OUT, "cover-free.png" if free else "cover.png"); im.save(p); print("wrote", p)


def onepager(free=False):
    im = Image.new("RGB", (1240, 1754), "white")  # A4 @150dpi
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1240, 14], fill=ACC)
    y = 70
    d.text((80, y), "TM Watch — how your free 30-day watch works" if free else
           "TM Watch — how your watch works", fill=INK, font=F(44)); y += 70
    d.text((80, y), "Thank you for starting a free 30-day watch on one mark. No card, no account, no renewal."
           if free else "Thank you for buying a 12-month watch for one mark.", fill=MUT, font=F(26)); y += 60
    steps = [
        "1. At checkout you entered the exact text of your mark. That is all we need — no account to create.",
        "2. Within one refresh cycle (at most 24 hours) your own private alert page goes live. Open",
        "   apventureengine.github.io/trademark-watch/alerts/ , type your mark, the email address you used",
        "   at checkout and the passphrase you chose in the checkout box, and it opens your page. Your",
        "   browser works out the address locally, so the passphrase never leaves your computer and nobody",
        "   who knows only your trademark and your email can open the page. Bookmark it, or subscribe to",
        "   its RSS feed (link at the top). Optional: if you gave a GitHub username at checkout you also",
        "   get invited to a private repo with the same alerts as files.",
        "3. Every Tuesday the USPTO publishes the Trademark Official Gazette: ~10,000 applications",
        "   published for opposition plus all registrations issued. The same day we match every word mark",
        "   in it against yours (edit distance + phonetic code + common variants) and post any hits to your",
        "   alert page and its RSS feed. Quiet weeks are logged as checked. No hits = no noise.",
        "4. A mark published for opposition can be opposed, or an extension of time requested, for 30 days",
        "   from its Gazette date. Each alert row links to the mark's live USPTO TSDR status page.",
        ("5. Your free watch stops after 30 days; your alert page then shows an 'expired' banner and a link to"
         if free else
         "5. Two weeks before your watch expires you get an expiry-reminder.md file. No auto-renewal."),
    ]
    if free:
        steps.append("   keep watching for %s / mark / year (one-time, 12 months, no auto-renewal)." % PRICE)
        steps.append("   Nothing is ever charged automatically.")
    for s in steps:
        d.text((80, y), s, fill=INK, font=F(24)); y += 36
    y += 30
    d.text((80, y), "Sample alert (real: watched mark STELLANITE vs the 2026-09-01 issue)", fill=INK, font=F(26)); y += 46
    y = table(d, 80, y, ROWS, [120, 170, 160, 280, 60, 290], fs=19, rowh=38)
    y += 40
    for s in ("Not legal advice. A flag means 'a human should look', never an opinion on likelihood of confusion.",
              "Design-only marks (logos without words) are out of scope; the matcher is text-only.",
              "Refunds: full refund within 14 days of purchase, via Gumroad. Contact: reply to your Gumroad receipt",
              "or open an issue at github.com/APVentureEngine/trademark-watch/issues — both reach the operator.",
              "Matcher source + benchmark: github.com/APVentureEngine/trademark-watch"):
        d.text((80, y), s, fill=MUT, font=F(22)); y += 34
    p = os.path.join(OUT, "how-your-free-watch-works.pdf" if free else "how-your-watch-works.pdf")
    im.save(p, "PDF", resolution=150.0); print("wrote", p)


if __name__ == "__main__":
    cover(); cover(free=True); onepager(); onepager(free=True)
