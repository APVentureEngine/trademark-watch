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
python3 fulfill.py --selftest        # custom-field extraction + email welcome
python3 mailer.py --selftest         # Brevo payload/rails (no network)
python3 fetch_trtdxfap.py --selftest # legacy ODP path (kept; keyless now)
python3 tmog_parse.py --selftest     # ST.96 gazette parser
python3 fetch_tmog.py --selftest     # merge/window/new-key logic
python3 watch_run.py --selftest      # alert generation + expiry handling
python3 selftest_e2e.py              # synthetic TDXF -> full pipeline

# STAGE fetch: KEYLESS. Pull any new Official Gazette issue (public CDN, no
# API key — the ODP key is permanently unavailable, A010). FATAL if it fails:
# a silently stale dataset is worse than a loud crash (honesty rail).
python3 fetch_tmog.py

if [ -f marks.jsonl ]; then
  MODE=real
  python3 gen_index.py --in marks.jsonl --out site/index
  python3 gen_seo.py --in marks.jsonl --out site
else
  MODE=synth
  echo "SYNTH MODE: no marks.jsonl (fetch never succeeded) — local index only, no push"
  python3 gen_index.py --synthetic 5000 --out site/index
fi

if [ "$MODE" = "real" ]; then
  # sync site -> public repo (repo/ is the git clone of APVentureEngine/trademark-watch)
  cp site/index.html site/report.js repo/
  mkdir -p repo/index && cp site/index/*.json repo/index/
  cp site/sitemap.xml repo/ 2>/dev/null || echo "note: no sitemap.xml yet"
  cp site/robots.txt repo/robots.txt
  cp indexnow_key.txt "repo/$(cat indexnow_key.txt).txt"
  if [ -d site/filings ]; then
    mkdir -p repo/filings && cp site/filings/*.html repo/filings/
  fi
  ( cd repo
    git add -A
    if ! git diff --cached --quiet; then
      if ! git diff --cached --quiet -- sitemap.xml; then touch ../.sitemap_changed; fi
      git commit -m "index refresh $(date -u +%F)"
      git push https://x-access-token:$GITHUB_ORG_TOKEN@github.com/APVentureEngine/trademark-watch.git main
    fi
  )
  # IndexNow only when the URL set changed (warn-feed c52 policy); non-fatal.
  if [ -f .sitemap_changed ]; then
    rm -f .sitemap_changed
    python3 indexnow_submit.py || echo "WARN: indexnow submit failed (non-fatal)"
  fi
  # paid watches vs today's new filings -> alert files -> push alerts repo.
  # FATAL on failure (set -e): a paying subscriber silently missing alerts
  # is the worst failure this product can have.
  python3 watch_run.py
fi

# paid fulfillment: Gumroad sale -> alerts-repo invite + watchlist entry.
# Live-fired in BOTH modes (real API, 0 sales is a valid outcome). The
# "fulfill:" summary line below in stdout is the wiring proof (lesson c65).
python3 fulfill.py

echo "refresh complete: mode=$MODE $(date -u)"
