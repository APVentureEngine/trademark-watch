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

if [ -f marks.jsonl ]; then
  MODE=real
  # STAGE fetch (A010): fetch_trtdxfap.py must have written/refreshed marks.jsonl
  # before this script (or be called here once it exists — BACKLOG #1).
  python3 gen_index.py --in marks.jsonl --out site/index
else
  MODE=synth
  echo "SYNTH MODE: no marks.jsonl (A010 pending) — local index only, no push"
  python3 gen_index.py --synthetic 5000 --out site/index
fi

if [ "$MODE" = "real" ]; then
  # sync site -> public repo (repo/ is the git clone of APProj/trademark-watch)
  cp site/index.html site/report.js repo/
  mkdir -p repo/index && cp site/index/*.json repo/index/
  ( cd repo
    git add -A
    if ! git diff --cached --quiet; then
      git commit -m "index refresh $(date -u +%F)"
      git push https://x-access-token:$GITHUB_TOKEN@github.com/APProj/trademark-watch.git main
    fi
  )
  # TODO(A010+launch): sitemap + indexnow_submit.py once SEO pages exist;
  # watch_run.py (paid marks vs today's filings -> alert files -> push
  # tm-watch-alerts) — needs real daily data.
fi

# paid fulfillment: Gumroad sale -> alerts-repo invite + watchlist entry.
# Live-fired in BOTH modes (real API, 0 sales is a valid outcome). The
# "fulfill:" summary line below in stdout is the wiring proof (lesson c65).
python3 fulfill.py

echo "refresh complete: mode=$MODE $(date -u)"
