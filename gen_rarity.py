#!/usr/bin/env python3
"""TM Watch — token-rarity table for matcher rule 6 (matcher v2, c76).

Reads marks.jsonl (the live Gazette corpus), counts per-token document
frequency over each mark's DISTINCTIVE, plural-stripped tokens (exactly the
token view matcher.compare uses), and writes common-tokens.json:

  {"corpus_marks": N, "min_df": 10, "tokens": ["ABC", ...sorted...]}

Semantics (shared by matcher.py and matcher.js): a token is RARE iff it is
NOT in this list. So a token that never appears in the corpus (VEUVE,
GASPAR, EDELMAN) is rare; PACIFIC / IRON / DENTAL / NORTH (df 50–110 in the
Sep-2026 corpus) are common and must never fire the rare-token rule.
Shipping the COMMON set (≈4.6k tokens, ~50 KB) instead of the rare set
(≈120k) keeps the browser payload small.

Deterministic: same marks.jsonl -> byte-identical file. Output goes to
product/common-tokens.json (next to matcher.py) AND site/common-tokens.json
(fetched by index.html; refresh.sh copies it to the repo root so the repo
copy of matcher.py finds it too).

Usage: python3 gen_rarity.py [--in marks.jsonl] [--min-df 10] | --selftest
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import matcher  # noqa: E402

MIN_DF = 10


def mark_tokens(mark):
    """Distinctive, plural-stripped token SET for one mark (matcher's view)."""
    norm = matcher.normalize(mark)
    return {matcher._strip_plural(t) for t in matcher._distinctive(matcher._tokens(norm))}


def build(marks, min_df=MIN_DF):
    df = collections.Counter()
    n = 0
    for m in marks:
        n += 1
        df.update(mark_tokens(m))
    common = sorted(t for t, c in df.items() if c >= min_df)
    return {"corpus_marks": n, "min_df": min_df, "tokens": common}


def write(doc, paths):
    body = json.dumps(doc, separators=(",", ":"), sort_keys=True) + "\n"
    for p in paths:
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w") as f:
            f.write(body)
    return body


def selftest():
    ok = True
    marks = ["PACIFIC CREST"] * 12 + ["VEUVE ROYALE", "IRON HORSE", "IRONS"] + ["IRON PEAK"] * 9
    doc = build(marks, 10)
    if doc["corpus_marks"] != 24:
        ok = False; print("FAIL corpus count", doc["corpus_marks"])
    # PACIFIC df=12, IRON df=11 (IRONS plural-strips to IRON), CREST 12, PEAK 9
    if doc["tokens"] != ["CREST", "IRON", "PACIFIC"]:
        ok = False; print("FAIL tokens", doc["tokens"])
    if build(marks, 10) != doc:
        ok = False; print("FAIL non-deterministic")
    print("gen_rarity selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    src = argv[argv.index("--in") + 1] if "--in" in argv else os.path.join(HERE, "marks.jsonl")
    min_df = int(argv[argv.index("--min-df") + 1]) if "--min-df" in argv else MIN_DF
    with open(src) as f:
        marks = (json.loads(ln)["mark"] for ln in f if ln.strip())
        doc = build(marks, min_df)
    body = write(doc, [os.path.join(HERE, "common-tokens.json"),
                       os.path.join(HERE, "site", "common-tokens.json")])
    print("gen_rarity: %d marks -> %d common tokens (df>=%d), %d bytes"
          % (doc["corpus_marks"], len(doc["tokens"]), min_df, len(body)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
