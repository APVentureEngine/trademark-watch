#!/bin/bash
# TM Watch daily refresh. Usage: bash refresh.sh   (any cwd; cds itself)
# Modes:
#   marks.jsonl present  -> REAL mode: build index from it, sync site into
#                           repo/, commit+push public repo, run watch runner.
#   marks.jsonl absent   -> SYNTH mode (pre-A010): build synthetic index for
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
python3 fulfill.py --selftest        # custom-field extraction
python3 fetch_trtdxfap.py --selftest # merge/window/new-serial logic
python3 watch_run.py --selftest      # alert generation + expiry handling
python3 selftest_e2e.py              # synthetic TDXF -> full pipeline

# STAGE fetch (A010): with the key in env, pull new daily files first.
# FATAL if it fails while a key is present — a silently stale dataset is
# worse than a loud crash (honesty rail).
if [ -n "$USPTO_ODP_API_KEY" ]; then
  python3 fetch_trtdxfap.py
fi

if [ -f marks.jsonl ]; then
  MODE=real
  python3 gen_index.py --in marks.jsonl --out site/index
  python3 gen_seo.py --in marks.jsonl --out site
else
  MODE=synth
  echo "SYNTH MODE: no marks.jsonl (A010 pending) — local index only, no push"
  python3 gen_index.py --synthetic 5000 --out site/index
fi

if [ "$MODE" = "real" ]; then
  # sync site -> public repo (repo/ is the git clone of APProj/trademark-watch)
  cp site/index.html site/report.js repo/
  mkdir -p repo/index && cp site/index/*.json repo/index/
  cp site/sitemap.xml repo/ 2>/dev/null || echo "note: no sitemap.xml yet"
  if [ -d site/filings ]; then
    mkdir -p repo/filings && cp site/filings/*.html repo/filings/
  fi
  ( cd repo
    git add -A
    if ! git diff --cached --quiet; then
      git commit -m "index refresh $(date -u +%F)"
      git push https://x-access-token:$GITHUB_TOKEN@github.com/APProj/trademark-watch.git main
    fi
  )
  # paid watches vs today's new filings -> alert files -> push alerts repo.
  # FATAL on failure (set -e): a paying subscriber silently missing alerts
  # is the worst failure this product can have.
  python3 watch_run.py
  # TODO(launch): IndexNow ping once Pages is enabled and sitemap is live.
fi

# paid fulfillment: Gumroad sale -> alerts-repo invite + watchlist entry.
# Live-fired in BOTH modes (real API, 0 sales is a valid outcome). The
# "fulfill:" summary line below in stdout is the wiring proof (lesson c65).
python3 fulfill.py

echo "refresh complete: mode=$MODE $(date -u)"
