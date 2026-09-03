#!/usr/bin/env python3
"""Public CSV downloads + dataset page for the Gazette corpus.

Output (into site/):
  site/data/issues/<transaction_date>.csv  one immutable CSV per Gazette issue
  site/data/latest.csv                     copy of the newest issue (stable URL)
  site/data/manifest.json                  every issue we have ever published
  site/data/index.html                     dataset landing page + rich JSON-LD

Why this exists (c87): the free similarity checker already publishes every
mark in the 120-day window as JSON search shards, so a plain CSV leaks nothing
new — but it turns the same public-domain data into something citable and
reusable, and it gives the schema.org Dataset markup a REAL DataDownload.
Google Dataset Search and HF are the only discovery channels a static
github.io site can win without a human pitching anyone; a Dataset node with no
distribution is not indexable as a dataset at all (warn-feed's landing page
has had distribution since day one; this one did not).

Issue files are IMMUTABLE and accumulate: marks.jsonl keeps only a 120-day
window, but files already written to site/data/issues stay, so the public
archive grows past the window with no extra storage cost in the pipeline.

Deterministic: every value derives from marks.jsonl (no wall clock), so a
re-run with unchanged input produces byte-identical files and an empty git
diff. Stdlib only.

Usage: python3 gen_data.py --in marks.jsonl --out site [--base URL]
"""
import csv
import json
import os
import sys

import gen_seo

BASE_DEFAULT = gen_seo.BASE_DEFAULT
COLUMNS = ["serial", "mark", "owner", "classes", "event", "status",
           "filing_date", "pub_date", "transaction_date"]
HF_URL = "https://huggingface.co/datasets/APProjects/uspto-trademark-gazette-word-marks"
LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"


def _row(r):
    out = dict((c, r.get(c, "")) for c in COLUMNS)
    out["classes"] = " ".join(str(c) for c in (r.get("classes") or []))
    return out


def write_issues(rows, data_dir):
    """One CSV per Gazette transaction date. Returns {date: (rows, bytes)}."""
    idir = os.path.join(data_dir, "issues")
    os.makedirs(idir, exist_ok=True)
    by_issue = {}
    for r in rows:
        d = r.get("transaction_date") or r.get("pub_date") or ""
        if d:
            by_issue.setdefault(d, []).append(r)
    for d, rs in by_issue.items():
        rs = sorted(rs, key=lambda r: r["serial"])
        path = os.path.join(idir, "%s.csv" % d)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            w.writeheader()
            for r in rs:
                w.writerow(_row(r))
    # manifest covers everything on disk, including issues that have since
    # aged out of the 120-day marks.jsonl window.
    manifest = {}
    for name in sorted(os.listdir(idir)):
        if name.endswith(".csv"):
            p = os.path.join(idir, name)
            # csv.reader, not line count: a handful of owner/mark values
            # contain embedded newlines and would inflate a naive count.
            with open(p, newline="") as f:
                n = sum(1 for _ in csv.reader(f)) - 1
            manifest[name[:-4]] = {"rows": n, "bytes": os.path.getsize(p),
                                   "csv": "issues/%s" % name}
    return manifest


def build(rows, out_dir, base):
    data_dir = os.path.join(out_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    manifest = write_issues(rows, data_dir)
    issues = sorted(manifest)
    newest = issues[-1] if issues else "n/a"
    oldest = issues[0] if issues else "n/a"
    total = sum(v["rows"] for v in manifest.values())

    # stable-URL copy of the newest issue
    if issues:
        src = os.path.join(data_dir, "issues", "%s.csv" % newest)
        with open(src) as f:
            latest = f.read()
        with open(os.path.join(data_dir, "latest.csv"), "w") as f:
            f.write(latest)

    with open(os.path.join(data_dir, "manifest.json"), "w") as f:
        json.dump({"dataset": "USPTO Official Gazette word marks",
                   "license": LICENSE_URL,
                   "columns": COLUMNS,
                   "latest_issue": newest,
                   "total_rows": total,
                   "issues": manifest}, f, indent=1, sort_keys=True)
        f.write("\n")

    raw = ("https://raw.githubusercontent.com/APVentureEngine/"
           "trademark-watch/main/data")
    rowsh = "".join(
        "<tr><td><a href=\"issues/%s.csv\">%s.csv</a></td><td>%s</td>"
        "<td>%s KB</td></tr>"
        % (d, d, "{:,}".format(manifest[d]["rows"]),
           "{:,}".format(round(manifest[d]["bytes"] / 1024)))
        for d in reversed(issues))

    body = (
        "<h1>US trademark Gazette word marks — free weekly CSV</h1>"
        "<p>Every mark the USPTO published for opposition or registered, "
        "normalized to one flat schema, one CSV per weekly "
        "<em>Official Gazette</em> issue. "
        "%s rows across %d issues (%s to %s). No login, no rate limit, "
        "public domain.</p>"
        "<p><a class=\"cta\" href=\"latest.csv\">Download the latest issue "
        "(%s)</a> &nbsp; <a href=\"manifest.json\">manifest.json</a> &nbsp; "
        "<a href=\"%s\">Same data on Hugging Face</a></p>"
        "<h2>Columns</h2>"
        "<p class=note><code>%s</code> — <code>event</code> is "
        "<code>published</code> (published for opposition, the 30-day window "
        "opens on <code>pub_date</code>) or <code>registered</code>; "
        "<code>classes</code> is a space-separated list of international "
        "classes; <code>serial</code> links to USPTO TSDR.</p>"
        "<h2>How it is built</h2>"
        "<p class=note>Fetched from the USPTO Trademark Official Gazette "
        "weekly XML, parsed and normalized by "
        "<a href=\"https://github.com/APVentureEngine/trademark-watch\">this "
        "open-source pipeline</a>, republished after every Tuesday issue. "
        "Issue files are never rewritten, so a URL you cite today keeps "
        "returning the same bytes. Our matcher's precision on real §2(d) "
        "refusal pairs is published in "
        "<a href=\"../benchmark/RESULTS.txt\">benchmark/RESULTS.txt</a>.</p>"
        "<h2>Licence</h2>"
        "<p class=note>USPTO Gazette records are US Government works in the "
        "public domain; this compilation is released under "
        "<a href=\"%s\">CC0 1.0</a>. Attribution is welcome, not required.</p>"
        "%s"
        "<h2>Issues</h2>"
        "<table><tr><th>Issue (CSV)</th><th>Marks</th><th>Size</th></tr>"
        "%s</table>"
        % ("{:,}".format(total), len(issues), oldest, newest, newest, HF_URL,
           ", ".join(COLUMNS), LICENSE_URL, gen_seo.cta(base), rowsh))

    jsonld = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": "USPTO Official Gazette word marks — weekly CSV",
        "description": ("Every US trademark published for opposition or "
                        "registered in the USPTO Official Gazette, normalized "
                        "to one flat schema (serial, mark, owner, classes, "
                        "event, filing/publication dates), one CSV per weekly "
                        "issue. %s rows, %d issues, updated after every "
                        "Tuesday Gazette."
                        % ("{:,}".format(total), len(issues))),
        "url": base + "/data/",
        "sameAs": HF_URL,
        "license": LICENSE_URL,
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "TM Watch",
                    "url": base + "/"},
        "keywords": ["trademarks", "USPTO", "Official Gazette",
                     "intellectual property", "trademark applications",
                     "opposition period", "public records"],
        "temporalCoverage": "%s/%s" % (oldest, newest),
        "spatialCoverage": {"@type": "Place", "name": "United States"},
        "dateModified": newest,
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "text/csv",
             "name": "Latest Gazette issue (CSV)",
             "contentUrl": raw + "/latest.csv"},
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "name": "Issue manifest",
             "contentUrl": raw + "/manifest.json"},
        ],
    }
    with open(os.path.join(data_dir, "index.html"), "w") as f:
        f.write(gen_seo.page(
            "US trademark Gazette word marks — free weekly CSV (%s issues, "
            "updated %s)" % (len(issues), newest),
            body, base, base + "/data/", jsonld))
    return len(issues), total


def main(argv):
    here = os.path.dirname(os.path.abspath(__file__))
    src = argv[argv.index("--in") + 1] if "--in" in argv else os.path.join(here, "marks.jsonl")
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(here, "site")
    base = argv[argv.index("--base") + 1] if "--base" in argv else BASE_DEFAULT
    rows = []
    with open(src) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    n, total = build(rows, out, base)
    print("gen_data: %d issue CSVs, %d rows -> %s/data" % (n, total, out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
