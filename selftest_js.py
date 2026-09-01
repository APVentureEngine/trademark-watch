#!/usr/bin/env python3
"""Cross-implementation parity gate: matcher.js must equal matcher.py.

No Node on this machine and the GitHub PAT lacks `workflow` scope (verified
c65), so JS runs INSIDE quickjs (pip, .venv here). This is the binding
pre-launch gate from INDEX_DESIGN.md's port checklist: identical flag +
reason kinds + phonetic codes + normalized forms on every parity vector,
PLUS a live re-check against matcher.py (not just the frozen JSON).

Run: ventures/tm-watch/product/.venv/bin/python3 selftest_js.py   (any cwd)
Exit 0 iff zero mismatches and recall >= 0.80. Wire into the future
refresh.sh BEFORE any push that touches matcher.js or the index generator.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import quickjs  # noqa: E402
from matcher import compare as py_compare  # noqa: E402

ctx = quickjs.Context()
ctx.eval(open(os.path.join(HERE, "matcher.js")).read())
ctx.eval("""
function _run(m1, m2) {
  var r = tmMatcher.compare(m1, m2);
  return JSON.stringify({flag: r.flag,
    kinds: r.reasons.map(function (x) { return x.split("(")[0]; }),
    phon1: r.detail.phon1, phon2: r.detail.phon2,
    norm1: r.detail.norm1, norm2: r.detail.norm2});
}
function _phon(s) { return tmMatcher.metaphoneLite(tmMatcher.normalize(s)); }
""")

doc = json.load(open(os.path.join(HERE, "parity-vectors.json")))
mismatch = 0
must = flagged = 0

for v in doc["vectors"]:
    js = json.loads(ctx.eval(f"_run({json.dumps(v['m1'])}, {json.dumps(v['m2'])})"))
    # live python ground truth (guards against a stale vectors file)
    pflag, preasons, pdetail = py_compare(v["m1"], v["m2"])
    py = {"flag": pflag, "kinds": [r.split("(")[0] for r in preasons],
          "phon1": pdetail["phon1"], "phon2": pdetail["phon2"],
          "norm1": pdetail["norm1"], "norm2": pdetail["norm2"]}
    if js != py:
        mismatch += 1
        print(f"MISMATCH {v['m1']!r} vs {v['m2']!r}\n  py={py}\n  js={js}")
    frozen = {k: v[k] for k in ("flag", "kinds", "phon1", "phon2", "norm1", "norm2")}
    if py != frozen:
        mismatch += 1
        print(f"STALE-VECTORS {v['m1']!r} vs {v['m2']!r}: regenerate with gen_vectors.py")
    if v["expect"] == "yes":
        must += 1
        flagged += int(js["flag"])

for p in doc["phonetic"]:
    code = ctx.eval(f"_phon({json.dumps(p['s'])})")
    if code != p["code"]:
        mismatch += 1
        print(f"PHONETIC-MISMATCH {p['s']!r}: py={p['code']} js={code}")

recall = flagged / must if must else 0.0
print(f"parity: {len(doc['vectors'])} vectors, {mismatch} mismatches; "
      f"JS recall {flagged}/{must} = {recall:.2f}")
if mismatch or recall < 0.80:
    print("SELFTEST-JS FAIL")
    sys.exit(1)
print("SELFTEST-JS PASS")
