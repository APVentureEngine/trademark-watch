#!/usr/bin/env python3
"""TM Watch matcher selftest — binding launch gate (KILL_CRITERIA #2).

Runs matcher.compare over:
  - state/research/tm-benchmark-pairs.csv  (real s.2(d) pairs; recall gate >=80%
    on rows where matcher_should_flag == 'yes')
  - ventures/tm-watch/product/negative-controls.csv (noise gate: report FP rate)

Exit 0 iff recall >= 0.80. Prints a full per-pair table for the log.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from matcher import compare  # noqa: E402

# engine root = 3 dirs up from product/ (fixed c66: os.getcwd() broke when
# refresh.sh cd'd into product/ — resolve from __file__, never from cwd)
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.join(ROOT, "state/research/tm-benchmark-pairs.csv")
if not os.path.exists(BENCH):  # public-repo layout: CSVs live in benchmark/
    BENCH = os.path.join(HERE, "benchmark", "tm-benchmark-pairs.csv")
NEG = os.path.join(HERE, "negative-controls.csv")
if not os.path.exists(NEG):
    NEG = os.path.join(HERE, "benchmark", "negative-controls.csv")


def run():
    must_flag, flagged_must = 0, 0
    acceptable, flagged_acceptable = 0, 0
    rows = []
    with open(BENCH) as f:
        for row in csv.DictReader(f):
            flag, reasons, _ = compare(row["mark1"], row["mark2"])
            expect = row["matcher_should_flag"].strip()
            if expect == "yes":
                must_flag += 1
                flagged_must += int(flag)
                status = "OK" if flag else "MISS"
            else:  # acceptable-flag: either outcome fine, report only
                acceptable += 1
                flagged_acceptable += int(flag)
                status = "ok(any)"
            rows.append((status, row["mark1"], row["mark2"], ",".join(reasons) or "-"))

    neg_total, neg_flagged = 0, 0
    neg_rows = []
    with open(NEG) as f:
        for row in csv.DictReader(f):
            neg_total += 1
            flag, reasons, _ = compare(row["mark1"], row["mark2"])
            neg_flagged += int(flag)
            status = "FP" if flag else "OK"
            neg_rows.append((status, row["mark1"], row["mark2"], ",".join(reasons) or "-"))

    print("== BENCHMARK (real s.2(d) pairs) ==")
    for r in rows:
        print(f"  [{r[0]:7s}] {r[1]!r} vs {r[2]!r}  -> {r[3]}")
    print("== NEGATIVE CONTROLS ==")
    for r in neg_rows:
        print(f"  [{r[0]:7s}] {r[1]!r} vs {r[2]!r}  -> {r[3]}")

    recall = flagged_must / must_flag if must_flag else 0.0
    fp_rate = neg_flagged / neg_total if neg_total else 0.0
    print()
    print(f"RECALL (must-flag): {flagged_must}/{must_flag} = {recall:.0%}  (gate: >=80%)")
    print(f"ACCEPTABLE-FLAG rows flagged: {flagged_acceptable}/{acceptable} (informational)")
    print(f"NEGATIVE-CONTROL false positives: {neg_flagged}/{neg_total} = {fp_rate:.0%}")
    gate = recall >= 0.80
    print(f"GATE: {'PASS' if gate else 'FAIL'}")
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(run())
