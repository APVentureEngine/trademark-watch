# TM Watch matcher — benchmark report (v1 2026-09-01 c64 · v2 2026-09-02 c76)

Binding launch gate (KILL_CRITERIA #2): flag ≥80% of a ≥20-pair benchmark of
real §2(d) opposition/refusal name pairs, without drowning in noise.

## Result v2.1 (2026-09-02, cycle 77): PASS — 36/36 must-flag, 0/20 FPs; token-phonetic noise cut

Rule 5's per-token phonetic equality (`_token_match` / `tokenMatch`) accepted
any equal metaphone-lite code for tokens of ≥3 letters. Codes can be one or
two characters (VEUVE → "F", ALE → "AL", YOGA → "AK"), so a single-token mark
with the same short code satisfied the 1/1 token ratio and flagged:
"Veuve Royale" flagged VIII, FIVE, FYI, FAFO, HAFIFA; "Gaspar's Ale" flagged
ALLU, OLLY, IUL; "Blue Lotus Yoga" flagged ACA, EGA, AIC. Measured on the
live 203,147-mark corpus with the same harness as v2 (every mark compared
to the query; hits attributed to the rule that fired):

| query | v2 total hits | v2 token-only junk | v2.1 total | v2.1 token-only (first 3) |
|---|---:|---:|---:|---:|
| Veuve Royale | 289 | 212 | 78 | 1 (ROYAL SERVICE) |
| Gaspar's Ale | 139 | 137 | 12 | 10 (ALA, ALAÏA, ALEO — one edit from ALE) |
| Kodiak Coffee | 144 | 127 | 33 | 16 (CADEKEO, COFFEE &, CUDACO) |
| Blue Lotus Yoga | ~290 (run cut; c77 note) | — | 23 | 17 (BLUE SYSTEM, HALTZ, HEALTHYHAUS) |
| Tesla Motors | not measured | — | 17 | 12 (HOTCELL, HOTZILLA, HUITSOL) |
| Patagonia Provisions | not measured | — | 6 | 1 (PETQUEEN) |
| Redwood Labs | not measured | — | 16 | 0 |
| Northstar Dental | not measured | — | 10 | 2 (DAWNTALE, DENTELLE) |
| Pacific Brew | not measured | — | 1 | 0 |
| Sunrise Bakery | not measured | — | 27 | 25 (BAIGUER, BAKEHER, BAKR) |
| Iron Peak Fitness | not measured | — | 61 | 57 (A ARENA, AARONAI, AERION) |
| Lumina Skin | not measured | — | 71 | 60 (CIKON, CO-SIGN, HILLMOON) |
| Apex Logistics | not measured | — | 22 | 20 (A APEX, AEPOCH, APACHE) |
| Vivid Vape | not measured | — | 6 | 0 |
| Hafifa | not measured | — | 2 | 0 |

Measured 2026-09-02 (cycles 77–79) on the 203,147-mark corpus of the
2026-09-01 issue. The v2 baseline run was stopped after three queries to free
the CPU, so most "before" cells are honestly blank rather than reconstructed.
Harness: every mark in `marks.jsonl` compared to the query, hits attributed
to the rule that fired; "token-only" = flagged by rule 5 (token overlap) and
by nothing else. All 15 queries of the fixed set measured (913 s single-run).

**What v2.1 still gets wrong (open, measured, not yet fixed):** the guard only
covers 1–2 character codes. Three-character codes are still weak evidence for
common English words: IRON → "ARN" matches AIRN/AERION/A ARENA (57 token-only
hits for "Iron Peak Fitness"), BAKERY → "BKR" matches BAKR/BCR/BGRY (25 for
"Sunrise Bakery"), LUMINA → "LMN" / SKIN → "SKN" match HILLMOON/HOLMAN/CIKON
(60 for "Lumina Skin"). The remaining noise is concentrated in queries whose
distinctive token is a short common word. Candidate fix, to be measured with
the same harness before it ships: require a phonetic token match to also be
within two edits of the query token, or to share the first letter.

Fix: a phonetic token match now requires the shared code to be ≥3 characters,
OR (short code AND the two tokens within one edit, e.g. ALE/AIL). Three-plus
character codes (LUMINA/LUMEENA → "LMN") are unchanged. Recall on the 45-pair
benchmark is unchanged at 36/36; negative controls 0/20; 123 parity vectors
(7 new for this guard) 0 mismatches between Python and JS.

## Result v2 (2026-09-02, cycle 76): PASS — 36/36 must-flag (100%), 0/20 negative-control FPs

Rule 6 "rare-token" added to matcher.py + matcher.js (parity: 116 vectors, 0
mismatches). Design: `gen_rarity.py` counts per-token document frequency over
the distinctive, plural-stripped tokens of every mark in the live Gazette
corpus (203,147 marks on 2026-09-02) and ships the COMMON set (df ≥ 10 →
4,571 tokens, 39 KB) as `common-tokens.json`; a token is rare iff absent from
it. Two marks that share one EXACT (or plural-stripped) distinctive token of
≥4 letters that is rare → flag, even when the 2/3 token-overlap rule does not
fire. VEUVE and GASPAR have df 0; PACIFIC 51, IRON 108, DENTAL 81, NORTH 106
(the negative controls) are common and stay silent.

What was measured before shipping, on the real corpus:
- First draft reused rule 5's token matcher INCLUDING phonetic equality.
  Metaphone-lite codes are short (VEUVE → "F", GASPARS → "KSPRS"), so "Veuve
  Royale" gained +112 junk hits (FAFO GAMES, VIVI…, WAVY DAZE) and "Gaspar's
  Ale" matched XPRESS marks. Rejected.
- Shipped version = exact/plural share only. Over 15 realistic queries the
  rule added 0–7 hits each (mean +1.7), every one sharing the actual rare word:
  KODIAK OUTDOORS → KODIAK BUILDING PARTNERS, TESLA ENERGY → TESLA BOND,
  PATAGONIA PROVISIONS → PATAGONIA WELLNESS, REDWOOD CAPITAL → REDWOODS PRESS.
  Those are flags a paid watch SHOULD raise. Borderline: MARITIME (df 9) —
  descriptive words just under the line will occasionally fire; the df
  threshold is one constant (`MIN_DF` in gen_rarity.py) if that proves noisy.
- Known limitation: the corpus is a rolling ~120-day Gazette window, so
  rarity is measured against recent filings, not the whole register. The
  table is regenerated every refresh and `benchmark/RESULTS.txt` is rewritten
  from it, so a published number can never outlive the data it was true for.

## Result v1 (2026-09-02, benchmark expanded to 45 pairs): PASS — 34/36 must-flag (94%), 0/20 negative-control FPs

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
