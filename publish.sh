#!/bin/bash
# TM Watch PUBLISH stage (c98) — the post-fetch tail of refresh.sh, runnable
# alone so a copy/page change can ship without waiting 20h for the scrape
# guard (warn-feed c96 lesson: split SCRAPE and PUBLISH). Requires a real
# marks.jsonl (never publishes synthetic data). Takes the same flock as
# pipeline.sh so it can never overlap a refresh.
# Usage: cd ventures/tm-watch/product && bash publish.sh
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
exec 9>.pipeline.lock
if ! flock -n 9; then echo "publish: another run holds .pipeline.lock — skipped"; exit 0; fi
[ -f marks.jsonl ] || { echo "publish: no marks.jsonl (synth mode) — refusing to publish"; exit 1; }
[ -n "${GITHUB_ORG_TOKEN:-}" ] || { echo "publish: GITHUB_ORG_TOKEN missing"; exit 1; }

# gates for the generators this stage touches (fast; the matcher gates are refresh.sh's job)
python3 gen_compare.py --selftest
python3 gen_guides.py --selftest
python3 gen_llms.py --selftest
python3 selftest_e2e.py
python3 fulfill.py --selftest >/dev/null
python3 gen_alert_pages.py --selftest >/dev/null
python3 gen_jsonld.py --selftest

python3 gen_seo.py --in marks.jsonl --out site
python3 gen_data.py --in marks.jsonl --out site
python3 gen_compare.py --out site
python3 gen_guides.py --out site
python3 gen_llms.py --out site
python3 fulfill.py
python3 watch_run.py
python3 gen_alert_pages.py --out site
python3 gen_jsonld.py --out site

bash sync_repo.sh "site publish $(date -u +%F)"
python3 gum_assets.py price-check || echo "WARN: Gumroad listing disagrees with pricing.py — run: python3 gum_assets.py sync + fix description"
echo "publish complete: $(date -u)"
