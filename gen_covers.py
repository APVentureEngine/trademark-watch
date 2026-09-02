#!/usr/bin/env python3
"""Gumroad cover (1280x720 PNG) + one-page 'how your watch works' PDF for TM Watch.

Run with an interpreter that has Pillow (warn-feed's .venv has 12.x; no system
TTF fonts on the VM -> ImageFont.load_default(size=)). Content is a REAL alert
row set (Stellanite vs the 2026-09-01 Gazette), not lorem ipsum.
Outputs: ../assets/cover.png, ../assets/how-your-watch-works.pdf
"""
import os
from PIL import Image, ImageDraw, ImageFont

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


def cover():
    im = Image.new("RGB", (1280, 720), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1280, 12], fill=ACC)
    d.text((60, 48), "TM Watch", fill=ACC, font=F(34))
    d.text((60, 96), "You hear on day 0 of the 30-day opposition window.", fill=INK, font=F(46))
    d.text((60, 158), "Every Tuesday's USPTO Official Gazette matched against your mark. $49 / mark / year.", fill=MUT, font=F(26))
    d.text((60, 218), "Real alert — watched mark STELLANITE, issue 2026-09-01:", fill=INK, font=F(24))
    d.rectangle([60, 256, 1220, 256 + 40 * len(ROWS) + 4], outline=(223, 229, 240), width=2)
    table(d, 62, 258, ROWS, [130, 190, 170, 300, 70, 300], fs=21, rowh=40)
    y = 256 + 40 * len(ROWS) + 40
    for line in ("Open-source edit-distance + phonetic matcher, benchmarked on 24 real §2(d) pairs: 20/20 recall, 0 false positives.",
                 "Alerts land in your private GitHub repo; GitHub emails you. One-time payment, 12 months, 14-day refund."):
        d.text((60, y), line, fill=MUT, font=F(22)); y += 34
    d.rectangle([60, 640, 1220, 690], fill=ACC)
    d.text((80, 652), "Try it free first: apventureengine.github.io/trademark-watch", fill="white", font=F(26))
    p = os.path.join(OUT, "cover.png"); im.save(p); print("wrote", p)


def onepager():
    im = Image.new("RGB", (1240, 1754), "white")  # A4 @150dpi
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1240, 14], fill=ACC)
    y = 70
    d.text((80, y), "TM Watch — how your watch works", fill=INK, font=F(44)); y += 70
    d.text((80, y), "Thank you for buying a 12-month watch for one mark.", fill=MUT, font=F(26)); y += 60
    steps = [
        "1. Right after checkout you entered your mark text and GitHub username. Nothing else is needed.",
        "2. Within one refresh cycle (at most 24 hours) you receive a GitHub invitation to a private",
        "   repository. Accept it, then click 'Watch' -> 'All activity' so GitHub emails you on every alert.",
        "3. Every Tuesday the USPTO publishes the Trademark Official Gazette: ~10,000 applications",
        "   published for opposition plus all registrations issued. The same day we match every word mark",
        "   in it against yours (edit distance + phonetic code + common variants) and write any hits to",
        "   alerts/<your-username>/<date>.md in the repo. No hits = no file, no noise.",
        "4. A mark published for opposition can be opposed, or an extension of time requested, for 30 days",
        "   from its Gazette date. Each alert row links to the mark's live USPTO TSDR status page.",
        "5. Two weeks before your watch expires you get an expiry-reminder.md file. No auto-renewal.",
    ]
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
    p = os.path.join(OUT, "how-your-watch-works.pdf"); im.save(p, "PDF", resolution=150.0); print("wrote", p)


if __name__ == "__main__":
    cover(); onepager()
