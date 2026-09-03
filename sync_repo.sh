#!/bin/bash
# TM Watch — the ONE site->repo sync + push (c104). Called by BOTH refresh.sh
# (after a real scrape) and publish.sh (copy/page changes without a scrape).
# Before c104 the two scripts each carried their own cp list and they had
# drifted (assets + source files only in one of them; a launch-price-era gen_covers.py
# and a stale site/index.html sat in the public repo). Never add a cp line to
# refresh.sh or publish.sh again — add it here.
# Usage: bash sync_repo.sh "<commit message>"   (cwd must be product/)
set -e
cd "$(dirname "$0")"
MSG="${1:-site sync $(date -u +%F)}"
[ -n "${GITHUB_ORG_TOKEN:-}" ] || { echo "sync_repo: GITHUB_ORG_TOKEN missing"; exit 1; }

cp site/index.html site/compare.html site/opposition-window.html site/diy-trademark-watch.html site/trademark-watch-cost.html site/llms.txt site/report.js site/common-tokens.json repo/
rm -rf repo/alerts && cp -r site/alerts repo/alerts
cp benchmark-results.txt repo/benchmark/RESULTS.txt   # per-pair table, regenerated each refresh
mkdir -p repo/assets && cp ../assets/cover.png ../assets/cover-free.png ../assets/how-your-watch-works.pdf ../assets/how-your-free-watch-works.pdf repo/assets/   # Gumroad covers are fetched from these URLs (gum_assets.py)
mkdir -p repo/index && cp site/index/*.json repo/index/
cp site/sitemap.xml repo/ 2>/dev/null || echo "note: no sitemap.xml yet"
cp site/robots.txt repo/robots.txt
cp indexnow_key.txt "repo/$(cat indexnow_key.txt).txt"
if [ -d site/filings ]; then mkdir -p repo/filings && cp site/filings/*.html repo/filings/; fi
if [ -d site/data ]; then
  mkdir -p repo/data/issues
  cp site/data/index.html site/data/manifest.json site/data/latest.csv repo/data/
  cp site/data/issues/*.csv repo/data/issues/
fi
# the repo advertises "matcher and benchmark are open source": keep the SOURCE current too
cp pricing.py fetch_tmog.py fetch_trtdxfap.py fulfill.py gen_alert_pages.py gen_covers.py gen_compare.py gen_data.py gen_guides.py gen_index.py gen_llms.py gen_rarity.py gen_seo.py gen_vectors.py gum_assets.py hf_mirror.py indexnow_submit.py mailer.py matcher.js matcher.py parity-vectors.json pipeline.sh publish.sh refresh.sh repo_meta.py sync_repo.sh selftest.js selftest.py selftest_e2e.py selftest_js.py selftest_site.py tdxf_parse.py tmog_parse.py watch_run.py repo/
rm -rf repo/site   # pre-c104 stale copy of an old landing page; never recreate it
# price literals: every shipped surface must agree with pricing.py (audited AFTER generation)
python3 pricing.py --audit
python3 repo_meta.py || echo "WARN: repo_meta failed (non-fatal)"

( cd repo
  git add -A
  if ! git diff --cached --quiet; then
    if ! git diff --cached --quiet -- sitemap.xml; then touch ../.sitemap_changed; fi
    git commit -q -m "$MSG"
    git push -q https://x-access-token:$GITHUB_ORG_TOKEN@github.com/APVentureEngine/trademark-watch.git main
    echo "sync_repo: pushed $(git rev-parse --short HEAD)"
  else
    echo "sync_repo: nothing changed"
  fi
)
# IndexNow only when the URL set changed (warn-feed c52 policy); non-fatal.
if [ -f .sitemap_changed ]; then
  rm -f .sitemap_changed
  python3 indexnow_submit.py || echo "WARN: indexnow submit failed (non-fatal)"
fi
