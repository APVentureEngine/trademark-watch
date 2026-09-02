#!/bin/bash
# TM Watch daily pipeline — the job the engine runs on its own timer while the
# venture is DORMANT (and that any cycle runs by hand). Written c73.
# Thin self-logging wrapper around refresh.sh (gates -> fetch new Gazette
# issues -> rebuild index + SEO pages -> push -> watch runner (repo + email
# alerts) -> Gumroad fulfilment). Data moves weekly (Tuesday Gazette) but the
# run is daily so a new issue is picked up within 24h and sales are fulfilled
# within 24h as promised on the landing page.
# Usage: bash ventures/tm-watch/product/pipeline.sh
# Needs: product/.venv, $GITHUB_ORG_TOKEN, $GUMROAD_ACCESS_TOKEN (+BREVO_* for email).
# Logs: product/pipeline.log (append; tokens never printed).
set -uo pipefail
cd "$(dirname "$0")"
LOG=pipeline.log
MIN_GAP_SECONDS=$((20 * 3600))
STAMP=.pipeline.last
{
  echo "==== pipeline start $(date -u +%FT%TZ)"
  if [ -f "$STAMP" ]; then
    last=$(cat "$STAMP"); now=$(date -u +%s)
    if [ $((now - last)) -lt "$MIN_GAP_SECONDS" ]; then
      echo "skip: last refresh $(( (now - last) / 3600 ))h ago (< 20h)"
      echo "==== pipeline end (skipped) $(date -u +%FT%TZ)"
      exit 0
    fi
  fi
  if bash refresh.sh; then
    date -u +%s > "$STAMP"
    echo "refresh: OK"
  else
    echo "refresh: FAILED exit=$? (stamp not advanced; next run retries)"
  fi
  echo "==== pipeline end $(date -u +%FT%TZ)"
} 2>&1 | sed -E 's#x-access-token:[^@]*@#x-access-token:***@#g' | tee -a "$LOG"
