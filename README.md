# Trademark Watch (work in progress)

Free instant trademark-name similarity check over fresh USPTO filings, plus a
$49/yr automated per-mark watch. Launching soon.

- `matcher.py` / `matcher.js` — the deterministic similarity matcher (identical
  ports; CI enforces cross-implementation parity on every push via
  `selftest.js` + `parity-vectors.json`).
- `benchmark/tm-benchmark-pairs.csv` — 24 real §2(d) opposition/refusal pairs
  from public TTAB/Federal Circuit records (cited). Matcher v1: 100% recall,
  0 false positives on `benchmark/negative-controls.csv`.

**Not legal advice.** A flag means "a human should look" — never a legal
opinion on likelihood of confusion.
