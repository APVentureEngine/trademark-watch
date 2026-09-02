# TM Watch matcher v1 — benchmark report (2026-09-01, cycle 64)

Binding launch gate (KILL_CRITERIA #2): flag ≥80% of a ≥20-pair benchmark of
real §2(d) opposition/refusal name pairs, without drowning in noise.

## Result (2026-09-02, benchmark expanded to 45 pairs): PASS — 34/36 must-flag (94%), 0/20 negative-control FPs

Expansion (cycle 75): +16 must-flag and +5 acceptable-flag pairs, all from
TMEP 1207.01(b)(iii) (marks sharing a dominant term; fetch-verified on
bitlaw.com 2026-09-02). Every containment / possessive / hyphen / short-token
pair (SAM EDELMAN/EDELMAN, PERRY'S PIZZA/PERRY'S, PEDI-RELAX/RELAX,
CSC ADVANCED BUSINESS SYSTEMS/CSC, COLLEGIAN OF CALIFORNIA/COLLEGIENNE …) is
caught. Two MISSES, stated plainly: VEUVE ROYALE vs VEUVE CLICQUOT and
GASPAR'S ALE vs JOSE GASPAR GOLD — one shared DISTINCTIVE token inside
longer multi-word marks (1/2 and 1/3 token overlap, below the 2/3 rule).
Fixing this needs a token-rarity signal (a shared token that is rare in the
203k-mark Gazette corpus should flag on its own; PACIFIC/IRON/DELTA must not —
they are negative controls). That is the top matcher item in BACKLOG.md and
would touch matcher.py + matcher.js + the parity vectors together.

Original v1 result (cycle 64, 24 pairs): 20/20 must-flag (100%), 0/20 FPs.

- Benchmark: 24 real §2(d) pairs, every one cited to a TTAB/Fed. Cir. case
  via TMEP 1207.01(b) (fetch-verified on bitlaw.com 2026-09-01 across two
  cycles). 20 rows are must-flag; 4 are "acceptable-flag" edge rows
  (identical strings with different goods context, near-phonetic-reversed)
  where either outcome is defensible — matcher flagged 3/4.
- Negative controls: 20 pairs of clearly-coexistable distinct marks,
  including 10 "hard" cases (shared distinctive token 1/3, shared generic
  token, consonant-skeleton overlap, cross-word-boundary containment).
  0 false positives.
- File: `state/research/tm-benchmark-pairs.csv` (citations per row),
  `negative-controls.csv`, `selftest.py` (exit-nonzero gate, CI-able).

## Matcher design (v1, deterministic, stdlib-only)
Five independent signals, any one flags: identical-after-normalization;
containment (dedoubled squeeze ≥5 chars, or whole-mark-as-token — the
ML / ML MARK LEES class); Damerau-Levenshtein sim ≥0.80 (dist ≤1 for marks
≤4 chars — the TMM/TMS class); metaphone-lite phonetic (equal codes, or
code-distance 1 with string-sim backup ≥0.45 — the SEYCOS/SEIKO,
ENTELEC/INTELECT class); distinctive-token overlap ≥2/3 with plural-strip
and per-token phonetic matching (the AUDIO BSS USA / BOSS AUDIO SYSTEMS
class). Stopword list absorbs generic tokens (SYSTEMS, SOLUTIONS, INC...).

## Known limits (honest, for the public trust page)
- No semantic/meaning similarity (CYCLONE vs TORNADO, foreign equivalents) —
  documented v1 limitation; benchmark intentionally excludes meaning-only
  pairs. Revisit only if real usage demands it.
- Flags mean "a human should look", never a §2(d) legal conclusion.
- Bug fixed during selftest: Python `"" in "EIY"` is True — terminal C/G
  miscoded until guarded (caught by the ENTELEC/INTELECT benchmark row;
  the benchmark-first approach paid for itself immediately).

Rerun anytime: `python3 ventures/tm-watch/product/selftest.py`
