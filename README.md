# TM Watch — free trademark similarity check + $49/yr automated Gazette watch

**Free tool:** https://apventureengine.github.io/trademark-watch/ — type a
brand name, get an instant similarity report against every US trademark
published for opposition or registered in the last ~4 months. Runs entirely
in your browser over a static, sharded index; nothing you type leaves your
machine.

**Paid:** $49/yr per mark — every new USPTO Official Gazette issue (weekly,
Tuesdays) is matched against your mark and you get an alert file (GitHub
notifies you) the same day, while the 30-day opposition window is open.
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
  (identical ports; `selftest_js.py` enforces parity on 86 vectors before any
  push).
- `watch_run.py` — paid watches vs the latest issue → alert markdown → private
  alerts repo. `fulfill.py` — Gumroad sale → repo invite + watchlist entry.
- `refresh.sh` — runs every self-test gate first (fatal), then the above.

## Benchmark

`benchmark/tm-benchmark-pairs.csv` — 45 real §2(d) pairs from public TTAB /
Federal Circuit records (every row cited; 36 must-flag, 9 where either outcome
is defensible). Matcher v1: 34/36 must-flag pairs caught (94% recall), 0 false
positives on the 20 pairs in `benchmark/negative-controls.csv`. The two misses
(VEUVE ROYALE / VEUVE CLICQUOT, GASPAR'S ALE / JOSE GASPAR GOLD — one shared
distinctive token inside longer multi-word marks) are documented in
`MATCHER_REPORT.md` as the known v1 gap.

**Not legal advice.** A flag means "a human should look" — never a legal
opinion on likelihood of confusion.
