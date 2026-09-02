#!/usr/bin/env python3
"""Generate parity-vectors.json: ground truth from matcher.py for the JS port.

Each vector: {m1, m2, expect, flag, kinds, phon1, phon2, norm1, norm2}
  expect: "yes" (benchmark must-flag) | "any" (benchmark acceptable) |
          "neg" (negative control) | "parity" (parity-only case)
  flag/kinds/phon/norm: what matcher.py actually produced (kinds = reason
  text before any '(' — float formatting differs across languages, so the
  parity contract is flag + reason kinds + phonetic codes + normalized forms).

Run from engine root: .venv or system python3, stdlib only.
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from matcher import compare, metaphone_lite, normalize  # noqa: E402

BENCH = os.path.join(HERE, "../../../state/research/tm-benchmark-pairs.csv")
NEG = os.path.join(HERE, "negative-controls.csv")

# Adversarial/edge parity cases (hand-picked to exercise every code path):
PARITY_CASES = [
    ("", ""), ("A", ""), ("", "B"), ("A", "A"),
    ("NIKE", "NYKE"), ("Nike, Inc.", "NIKE"),
    ("BIGG'S", "BIGS"), ("Bigg’s", "BIGGS"),
    ("PHASE", "FAZE"), ("GHOST", "KOST"),  # digraph PH/GH
    ("SCHOOL", "SKOOL"), ("SHINE", "CHINE"),  # SCH/SH/CH -> X
    ("THINK", "TINK"), ("WHALE", "WALE"),  # TH/WH
    ("MAGIC", "MAJIK"), ("GEM", "JEM"), ("CITY", "SITY"),  # soft C/G
    ("LOGIC", "LOJIK"),  # terminal C after vowel (c64 bug class)
    ("ANALYTIC", "ANALYTICS"),  # terminal C + plural
    ("STRATEGIC", "STRATEJIK"),
    ("QUIK", "QUICK"), ("ZEBRA", "SEBRA"), ("VIVID", "FIFID"),
    ("XEROX", "ZEROKS"), ("WHO", "HOO"), ("OH", "O"),
    ("AAA", "A"), ("BOOKKEEPER", "BOKEPER"),  # dedouble
    ("H2O PLUS", "H20 PLUS"), ("MARK 7", "MARK SEVEN"),  # digits
    ("BLUE-SKY", "BLUESKY"), ("RED & BLACK", "RED AND BLACK"),
    ("A+ TUTORS", "A PLUS TUTORS"),
    ("CAFÉ OLÉ", "CAFE OLE"),  # unicode letters stripped by [^A-Z0-9]
    ("THE GLOBAL TECH GROUP", "GLOBAL SYSTEMS"),  # all-stopword tokens
    ("SUN VALLEY FARMS", "SUNVALLEY FARM"),
    ("IRONCLAD", "IRON CLAD SERVICES"),  # containment across spaces
    ("APEX", "APEXX LABS"),  # short + whole-mark-token
    ("ACME", "ACNE"),  # edit-short dist=1
    ("AB", "BA"),  # transposition, short
    ("W", "H"),  # both metaphone-empty
    ("YELLOW", "ELLO"),  # initial vowel Y handling
    # rule 6 (v2 rare-token) coverage — needs common-tokens.json present
    ("VEUVE ROYALE", "VEUVE CLICQUOT"),  # rare shared token -> flag
    ("GASPAR'S ALE", "JOSE GASPAR GOLD"),  # possessive-stripped rare share
    ("PACIFIC CREST FINANCIAL", "PACIFIC HARBOR MEDIA"),  # common share -> no
    ("KODIAK OUTDOORS", "KODIAK BUILDING PARTNERS"),  # rare exact share
    ("KODIAKS OUTDOORS", "KODIAK BUILDING"),  # plural-stripped rare share
    ("ZQX GAMES", "ZQX MEDIA"),  # rare but len<4 -> no rule 6
    ("TESLA ENERGY", "TESLA BOND"),
    ("FYOU PMEC", "VEUVE ROYALE"),  # phonetic-only share must NOT fire rule 6
    # v2.1 (c77) token phonetic guard: 1-2 char codes need tokens within 1 edit
    ("VEUVE ROYALE", "VIII"),  # code "F" == "F" but far apart -> no
    ("VEUVE ROYALE", "FIVE"),
    ("GASPAR'S ALE", "ALLU"),  # code "AL" == "AL", dist 2 -> no
    ("GASPAR'S ALE", "ALE HOUSE"),  # exact token -> tokens(1/1) still fires
    ("BREW ALE", "BREW AILE"),  # short code, dist 1 -> phonetic token still ok
    ("LUMINA", "LUMEENA SKIN"),  # 3+ char code -> unchanged
    ("KODIAK COFFEE", "KODIAC BREW"),  # ratio 1/2 < 0.67 -> no (unchanged)
    ("REDWOODS PRESS", "REDWOOD CAPITAL"),
]


def kinds(reasons):
    return [r.split("(")[0] for r in reasons]


def vec(m1, m2, expect):
    flag, reasons, detail = compare(m1, m2)
    return {
        "m1": m1, "m2": m2, "expect": expect, "flag": flag,
        "kinds": kinds(reasons),
        "phon1": detail["phon1"], "phon2": detail["phon2"],
        "norm1": detail["norm1"], "norm2": detail["norm2"],
    }


def main():
    out = []
    with open(BENCH) as f:
        for row in csv.DictReader(f):
            expect = "yes" if row["matcher_should_flag"].strip() == "yes" else "any"
            out.append(vec(row["mark1"], row["mark2"], expect))
    with open(NEG) as f:
        for row in csv.DictReader(f):
            out.append(vec(row["mark1"], row["mark2"], "neg"))
    for m1, m2 in PARITY_CASES:
        out.append(vec(m1, m2, "parity"))
    # standalone metaphone vectors for direct function parity
    phon = [{"s": s, "code": metaphone_lite(normalize(s))} for s, _ in PARITY_CASES]
    doc = {"generated_by": "gen_vectors.py (matcher.py ground truth)",
           "vectors": out, "phonetic": phon}
    path = os.path.join(HERE, "parity-vectors.json")
    with open(path, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    print(f"wrote {path}: {len(out)} vectors ({sum(1 for v in out if v['flag'])} flagged)")


if __name__ == "__main__":
    main()
