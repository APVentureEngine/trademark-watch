# TM Watch — free trademark similarity check + $29/yr automated Gazette watch

**Free tool:** https://apventureengine.github.io/trademark-watch/ — type a
brand name, get an instant similarity report against every US trademark
published for opposition or registered in the last ~4 months. Runs entirely
in your browser over a static, sharded index; nothing you type leaves your
machine. Every report has a permanent link that re-runs against the latest
issue, e.g. https://apventureengine.github.io/trademark-watch/?q=Kodiak%20Coffee
— each flagged serial links to its live USPTO TSDR status page.

**Paid:** $29/yr per mark, one payment, no auto-renewal — every new USPTO
Official Gazette issue (weekly, Tuesdays) is matched against your mark and any
hit lands on your private alert page + RSS feed the same day, while the 30-day
opposition window is open (a private GitHub alert repo is optional; plain email
alerts are not built yet). First 30 days free, no card:
https://approj.gumroad.com/l/tm-free-watch
https://approj.gumroad.com/l/pwvfma

## Data

USPTO **Trademark Official Gazette** weekly ST.96 XML — public, no API key:

- issue list: `https://tm-eog-service.uspto.gov/eog-rest-service/api/external/search/publications`
- issue XML: `https://cdn.uspto.gov/doc/TMOGIssue_YYYYMMDD_entire?extension=xml`

We keep two sections: *Applications publishing for opposition* and
*Registrations publishing* (~20k word marks per issue). Design-only marks
(no verbal element) are out of scope; cancellations/renewals are skipped.
Rolling 120-day window, regenerated after every issue.

The whole window as one CSV (serial, mark, event, Gazette date, filing date,
classes, owner, status), refreshed with every issue:
**https://huggingface.co/datasets/APProjects/uspto-gazette-word-marks**

Delivery for paid watches: email (primary, via `mailer.py`) plus an optional
private alert-history repo; both idempotent per watch per day.

## Pipeline (stdlib Python, deterministic)

- `fetch_tmog.py` — list issues → download new ones → `tmog_parse.py`
  (ST.96 → records) → `marks.jsonl` / `new_marks.jsonl`.
- `gen_index.py` — sharded client-side index (`site/index/shard-*.json`,
  phonetic-first-letter shards, precomputed metaphone + squeezed forms).
- `gen_seo.py` — per-class "newly published & registered" pages + sitemap.
- `matcher.py` / `matcher.js` — the deterministic similarity matcher
  (identical ports; `selftest_js.py` enforces parity on 116 vectors before any
  push). `gen_rarity.py` → `common-tokens.json`: the corpus common-word table
  behind the v2 rare-shared-word rule (regenerated from the live corpus each
  refresh; a word is "rare" iff it appears in <10 of the ~200k marks).
- `watch_run.py` — paid watches vs the latest issue → alert markdown → private
  alerts repo + `alert_history.json`. `gen_alert_pages.py` — one unlisted alert
  page + RSS feed per paid watch at `alerts/<sha256(mark|email)>/` (no account
  needed; `alerts/` is the finder, computed client-side). `fulfill.py` —
  Gumroad sale → watchlist entry (+ optional repo invite).
- `refresh.sh` — runs every self-test gate first (fatal), then the above.

## Benchmark

`benchmark/tm-benchmark-pairs.csv` — 45 real §2(d) pairs from public TTAB /
Federal Circuit records (every row cited; 36 must-flag, 9 where either outcome
is defensible). Matcher v2 (2026-09-02): 36/36 must-flag pairs caught, 0 false
positives on the 20 pairs in `benchmark/negative-controls.csv`. The two v1
misses (VEUVE ROYALE / VEUVE CLICQUOT, GASPAR'S ALE / JOSE GASPAR GOLD — one
shared distinctive token inside longer multi-word marks) are now caught by the
rare-shared-word rule; `MATCHER_REPORT.md` has the design, the measured noise
cost (+1.7 extra hits per query on the live corpus, all sharing the actual
rare word), and why phonetic token equality was deliberately excluded from it.
`benchmark/RESULTS.txt` is the full per-pair table, rewritten by every refresh
against the shipped `common-tokens.json` — if a corpus change ever moves a
result, that file changes with it, not this paragraph.

**Not legal advice.** A flag means "a human should look" — never a legal
opinion on likelihood of confusion.
