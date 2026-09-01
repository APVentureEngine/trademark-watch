#!/usr/bin/env python3
"""TM Watch — free-report client index generator (BACKLOG #5 impl, c66).

Input:  marks.jsonl — one JSON obj per line:
          {"serial": int, "mark": str, "filing_date": "YYYY-MM-DD", "classes": [int,...]}
        Produced later by the TRTDXFAP fetch+parse (blocked on A010). Until
        then, --synthetic N emits a deterministic fake-but-realistic file so
        the whole downstream (index -> site -> client JS) is testable keyless.

Output (into --out, default site/index/):
  manifest.json                {"base": "...", "generated": "...", "shards": {"K": rows, ...}, "total": n}
  shard-<CH>.json              {"marks": [[serial, "MARK", "YYYY-MM-DD", [classes], "PHON", "SQUEEZED"], ...]}

Sharding contract (client MUST mirror; see site/report.js):
  A mark lands in one shard per DISTINCT phonetic-first-char of its
  distinctive tokens (matcher.metaphone_lite per token). Fallbacks:
  no distinctive tokens -> use all tokens; empty phonetic code -> first char
  of the token; non A-Z0-9 -> "_". Digits shard as themselves.
  Client computes the same set for the QUERY's tokens and fetches those
  shards only, dedupes rows by serial, then runs full matcher.compare.

Deterministic: same input -> byte-identical output (sorted keys/rows, no
timestamps except manifest 'generated' which is taken from the newest
filing_date in the data, NOT the wall clock).

Usage:
  python3 gen_index.py --in marks.jsonl --out site/index
  python3 gen_index.py --synthetic 5000 --out site/index   (keyless dev/test)
  python3 gen_index.py --selftest
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import matcher  # noqa: E402


def shard_chars(mark_text):
    """Set of shard chars for a mark or query string. Mirrored in report.js."""
    norm = matcher.normalize(mark_text)
    toks = [t for t in norm.split(" ") if t]
    dis = [t for t in toks if t not in matcher.STOPWORDS] or toks
    chars = set()
    for t in dis:
        code = matcher.metaphone_lite(t)
        ch = (code or t or "_")[0]
        chars.add(ch if ch.isalnum() else "_")
    return chars or {"_"}


def build(rows, out_dir):
    shards = {}
    for r in rows:
        serial, mark, fdate, classes = r["serial"], r["mark"], r["filing_date"], r.get("classes", [])
        norm = matcher.normalize(mark)
        phon = matcher.metaphone_lite(norm)
        squeezed = matcher.dedouble(matcher.squeeze(norm))
        row = [serial, mark, fdate, sorted(classes), phon, squeezed]
        for ch in shard_chars(mark):
            shards.setdefault(ch, {})[serial] = row  # dedupe within shard
    os.makedirs(out_dir, exist_ok=True)
    # remove stale shards so renames don't leave orphans
    for f in os.listdir(out_dir):
        if f.startswith("shard-") and f.endswith(".json"):
            os.remove(os.path.join(out_dir, f))
    manifest = {"base": min((r["filing_date"] for r in rows), default=""),
                "generated": max((r["filing_date"] for r in rows), default=""),
                "total": len(rows), "shards": {}}
    for ch in sorted(shards):
        srows = [shards[ch][k] for k in sorted(shards[ch])]
        manifest["shards"][ch] = len(srows)
        with open(os.path.join(out_dir, "shard-%s.json" % ch), "w") as f:
            json.dump({"marks": srows}, f, separators=(",", ":"), sort_keys=True)
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    return manifest


def synthetic(n):
    """Deterministic fake filings: realistic-shaped names, no RNG (no seed drift)."""
    heads = ["NOVA", "APEX", "LUMEN", "CRISP", "KRISP", "VERDE", "ZEN", "BOLT",
             "NIMBUS", "FLUX", "EMBER", "QUARTZ", "ONYX", "PIXEL", "RIDGE",
             "TERRA", "VIVID", "HALO", "DRIFT", "FORGE", "NYKE", "ADIDAZ",
             "KODAC", "ZOOMLY", "BREWCO"]
    tails = ["", " LABS", " COFFEE", " TECHNOLOGIES", " STUDIO", " FOODS",
             " FITNESS", " CAPITAL", " ORGANICS", " MEDIA", " WORKS", " AI",
             " SUPPLY", " HEALTH", " GAMES"]
    rows = []
    for i in range(n):
        name = heads[i % len(heads)] + tails[(i // len(heads)) % len(tails)]
        if i % 7 == 0:
            name = name + " " + str(2000 + i % 90)
        day = i % 90
        rows.append({"serial": 90000000 + i, "mark": name,
                     "filing_date": "2026-%02d-%02d" % (6 + day // 30, 1 + day % 30),
                     "classes": [(i % 45) + 1]})
    return rows


def selftest():
    ok = True
    # 1. shard chars mirror phonetic coding: CRISP and KRISP must co-shard.
    if shard_chars("Crisp Coffee") != shard_chars("KRISP"):
        ok = False; print("FAIL: crisp/krisp shard mismatch")
    # 2. stopword-only mark falls back to tokens, never empty.
    if not shard_chars("The Group LLC"):
        ok = False; print("FAIL: stopword-only mark got no shard")
    # 3. build round-trip: every row reachable via its own shard_chars.
    rows = synthetic(500)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        man = build(rows, td)
        if man["total"] != 500:
            ok = False; print("FAIL: manifest total %s" % man["total"])
        loaded = {}
        for ch in man["shards"]:
            with open(os.path.join(td, "shard-%s.json" % ch)) as f:
                for r in json.load(f)["marks"]:
                    loaded.setdefault(ch, set()).add(r[0])
        for r in rows:
            chs = shard_chars(r["mark"])
            if not any(r["serial"] in loaded.get(ch, set()) for ch in chs):
                ok = False; print("FAIL: serial %s unreachable" % r["serial"]); break
        # 4. determinism: rebuild -> identical manifest bytes.
        with open(os.path.join(td, "manifest.json")) as f:
            m1 = f.read()
        build(rows, td)
        with open(os.path.join(td, "manifest.json")) as f:
            if f.read() != m1:
                ok = False; print("FAIL: non-deterministic manifest")
    print("gen_index selftest: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv):
    if "--selftest" in argv:
        return selftest()
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(HERE, "site", "index")
    if "--synthetic" in argv:
        rows = synthetic(int(argv[argv.index("--synthetic") + 1]))
    else:
        src = argv[argv.index("--in") + 1]
        with open(src) as f:
            rows = [json.loads(ln) for ln in f if ln.strip()]
    man = build(rows, out)
    print("gen_index: %d marks -> %d shards in %s (newest filing %s)"
          % (man["total"], len(man["shards"]), out, man["generated"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
