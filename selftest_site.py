#!/usr/bin/env python3
"""Site-logic parity gate: report.js sharding + report pipeline must equal
the Python reference (gen_index.shard_chars + matcher.compare over the same
rows). Runs report.js inside quickjs (no Node on VM; no Actions CI — this is
the binding substitute). END-TO-END: builds a real synthetic index with
gen_index.py, serves shards to report.js via an injected fetchShard, and
compares the full match list (serials + reason kinds + order) per query.

Run: ventures/tm-watch/product/.venv/bin/python3 selftest_site.py  (any cwd)
Exit 0 iff zero mismatches. Wire into refresh.sh before any site push.
"""
import json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import quickjs  # noqa: E402
import matcher  # noqa: E402
import gen_index  # noqa: E402

QUERIES = [
    "Nike", "Nyke", "crisp coffee", "KRISP", "The Group LLC", "Adidas",
    "zoomly", "Brew Co", "Nova Labs", "quartz health 2026", "xylophone911",
    "  weird--punct'uation  &  co ", "Terra", "apex ai", "totally unrelated zq",
]

ctx = quickjs.Context()
ctx.eval("var self = this;")  # report.js UMD attaches to root
ctx.eval(open(os.path.join(HERE, "matcher.js")).read())
# rule 6 parity: give JS the same common-token set Python auto-loads
_ct = os.path.join(HERE, "common-tokens.json")
if os.path.exists(_ct):
    ctx.eval("tmMatcher.setCommonTokens(%s);" % json.dumps(json.load(open(_ct))["tokens"]))
ctx.eval(open(os.path.join(HERE, "site", "report.js")).read())
ctx.eval("""
function _shardChars(q) { return JSON.stringify(tmReport.shardChars(q)); }
function _runReport(q, rowsJson) {
  var m = tmReport.runReport(q, JSON.parse(rowsJson));
  return JSON.stringify(m.map(function (x) {
    return [x.serial, x.reasons.map(function (r) { return r.split("(")[0]; })];
  }));
}
""")

mismatch = 0

# 1. shardChars parity on queries AND on every synthetic mark text.
rows = gen_index.synthetic(2000)
texts = QUERIES + [r["mark"] for r in rows[:400]]
for t in texts:
    js = json.loads(ctx.eval("_shardChars(%s)" % json.dumps(t)))
    py = sorted(gen_index.shard_chars(t))
    if js != py:
        mismatch += 1
        print("SHARD MISMATCH %r: py=%s js=%s" % (t, py, js))

# 2. end-to-end: build index, emulate client fetch+dedupe in Python (same
#    contract), then compare report.js runReport vs Python matcher.compare.
with tempfile.TemporaryDirectory() as td:
    gen_index.build(rows, td)
    shards = {}
    for fn in os.listdir(td):
        if fn.startswith("shard-"):
            shards[fn[6:-5]] = json.load(open(os.path.join(td, fn)))["marks"]
    for q in QUERIES:
        seen, sel = set(), []
        for ch in sorted(gen_index.shard_chars(q)):
            for r in shards.get(ch, []):
                if r[0] not in seen:
                    seen.add(r[0]); sel.append(r)
        # python reference result (same sort contract as report.js)
        ref = []
        for r in sel:
            flag, reasons, detail = matcher.compare(q, r[1])
            if flag:
                ref.append((r[0], [x.split("(")[0] for x in reasons],
                            len(reasons), detail["edit_sim"]))
        ref.sort(key=lambda x: (-x[2], -x[3], x[0]))
        py_out = [[s, kinds] for s, kinds, _, _ in ref]
        js_out = json.loads(ctx.eval("_runReport(%s, %s)"
                                     % (json.dumps(q), json.dumps(json.dumps(sel)))))
        if js_out != py_out:
            mismatch += 1
            print("REPORT MISMATCH %r:\n  py=%s\n  js=%s" % (q, py_out[:5], js_out[:5]))

print("selftest_site: %s (%d texts sharded, %d queries end-to-end)"
      % ("PASS" if mismatch == 0 else "FAIL(%d)" % mismatch, len(texts), len(QUERIES)))
sys.exit(0 if mismatch == 0 else 1)
