#!/bin/bash
# TM Watch refresh (run daily; data moves weekly — new Gazette every Tuesday).
# Usage: bash refresh.sh   (any cwd; cds itself)
# Modes:
#   marks.jsonl present  -> REAL mode: build index from it, sync site into
#                           repo/, commit+push public repo, run watch runner.
#   marks.jsonl absent   -> SYNTH mode (first run failed): build synthetic index for
#                           LOCAL testing only. NEVER pushes product surfaces
#                           (public site must never claim synthetic data is
#                           real USPTO data — honesty rail).
# Always: parity/self-test gates run FIRST and are FATAL (exit nonzero blocks
# everything — lesson c64/c65: gates before pushes, live-fire the whole
# script, no `|| true` on integration points that can hide path errors).
set -e
cd "$(dirname "$0")"
source .venv/bin/activate

echo "=== GATES (fatal) ==="
python3 selftest.py                  # benchmark recall/FP gate (§2(d) pairs)
python3 selftest_js.py               # matcher.js parity (quickjs)
python3 selftest_site.py             # report.js sharding+pipeline parity
python3 gen_index.py --selftest      # index build round-trip + determinism
python3 gen_rarity.py --selftest     # common-token table (matcher rule 6)
python3 fulfill.py --selftest        # custom-field extraction + email welcome
python3 mailer.py --selftest         # Brevo payload/rails (no network)
python3 fetch_trtdxfap.py --selftest # legacy ODP path (kept; keyless now)
python3 tmog_parse.py --selftest     # ST.96 gazette parser
python3 fetch_tmog.py --selftest     # merge/window/new-key logic
python3 watch_run.py --selftest      # alert generation + expiry handling
python3 gen_alert_pages.py --selftest # private alert pages + finder JS parity (c84)
python3 gen_compare.py --selftest    # comparison page: determinism + staleness marker (c97)
python3 gen_guides.py --selftest     # opposition-window guide: fees + staleness marker (c98)
python3 gen_llms.py --selftest       # llms.txt renders live corpus numbers (c97)
python3 selftest_e2e.py              # synthetic TDXF -> full pipeline

# STAGE fetch: KEYLESS. Pull any new Official Gazette issue (public CDN, no
# API key — the ODP key is permanently unavailable, A010). FATAL if it fails:
# a silently stale dataset is worse than a loud crash (honesty rail).
python3 fetch_tmog.py

if [ -f marks.jsonl ]; then
  MODE=real
  # rule-6 rarity table from the (possibly just-updated) corpus, then RE-RUN
  # the matcher gates against it: a new issue can move a token across the
  # df>=10 line, and the published benchmark claim must reflect the shipped
  # table, not last week's. Fatal (set -e).
  python3 gen_rarity.py --in marks.jsonl
  # c96: the frozen parity vectors bake in the rarity table; a token crossing
  # the df>=10 line makes them "STALE-VECTORS" and failed the whole refresh
  # (Sep 3, first run after 5 new issues). Re-freeze from live matcher.py
  # first; selftest_js still compares JS against LIVE python, so the gate
  # keeps its teeth (and the recall floor below is unchanged).
  python3 gen_vectors.py
  python3 selftest.py > benchmark-results.txt
  python3 selftest_js.py
  python3 gen_index.py --in marks.jsonl --out site/index
  python3 gen_seo.py --in marks.jsonl --out site
  # public CSV downloads + dataset page (c87). Issue files are immutable and
  # accumulate past the 120-day marks.jsonl window, so this never rewrites
  # history; git only sees the new issue each Tuesday.
  python3 gen_data.py --in marks.jsonl --out site
  # buyer-intent comparison page (c97): prices are hand-verified facts in
  # competitors.json, everything else is rendered from the live index.
  python3 gen_compare.py --out site
  # procedural explainer ("published for opposition, what now") -> free-watch CTA (c98)
  python3 gen_guides.py --out site
  # llms.txt for answer engines / coding agents (c97), rendered live.
  python3 gen_llms.py --out site
else
  MODE=synth
  echo "SYNTH MODE: no marks.jsonl (fetch never succeeded) — local index only, no push"
  python3 gen_index.py --synthetic 5000 --out site/index
fi

if [ "$MODE" = "real" ]; then
  # ORDER (c84): fulfill (new sales -> watchlist) -> watch_run (alerts +
  # alert_history.json) -> gen_alert_pages (private pages) -> ONE site sync
  # + push. A buyer's page therefore exists on the first refresh after the
  # sale (receipt promises <=24h).
  # paid fulfillment: Gumroad sale -> watchlist entry (+ optional repo invite).
  # Live-fired (real API, 0 sales is a valid outcome); the "fulfill:" summary
  # line in stdout is the wiring proof (lesson c65).
  python3 fulfill.py
  # paid watches vs today's new filings -> alert files/history -> push alerts repo.
  # FATAL on failure (set -e): a paying subscriber silently missing alerts
  # is the worst failure this product can have.
  python3 watch_run.py
  python3 gen_alert_pages.py --out site
  # sync site (+ current source) -> public repo and push: ONE script shared with publish.sh (c104)
  bash sync_repo.sh "index refresh $(date -u +%F)"
  # Hugging Face mirror (second discovery channel, c73). Non-fatal.
  if [ -n "${HF_TOKEN:-}" ]; then
    python3 hf_mirror.py 2>&1 | grep -v -i warning
    if [ "${PIPESTATUS[0]}" = "0" ]; then echo "hf_mirror: OK"; else echo "hf_mirror: FAILED (non-fatal)"; fi
  else
    echo "hf_mirror: HF_TOKEN absent, skipped"
  fi
else
  # synth mode: still live-fire fulfillment so the wiring line appears.
  python3 fulfill.py
fi

echo "refresh complete: mode=$MODE $(date -u)"
