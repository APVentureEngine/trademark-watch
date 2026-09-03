#!/usr/bin/env python3
"""Render the GitHub repo description from pricing.py (c104). Off-repo claim
surfaces must be RENDERED by the publish stage, never hand-patched — the repo
description still carried the launch price a full publish after the price moved.
Runs from sync_repo.sh; idempotent; non-fatal upstream."""
import json, os, sys, urllib.request
from pricing import PRICE_YR

REPO = "APVentureEngine/trademark-watch"
DESC = ("Free instant trademark similarity check over fresh USPTO Gazette filings + %s automated "
        "weekly watch (one payment, no auto-renewal). Informational alerts, not legal advice." % PRICE_YR)


def main():
    tok = os.environ.get("GITHUB_ORG_TOKEN")
    if not tok:
        print("repo_meta: GITHUB_ORG_TOKEN missing"); return 1
    hdr = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
           "Content-Type": "application/json"}
    cur = json.load(urllib.request.urlopen(urllib.request.Request(
        "https://api.github.com/repos/" + REPO, headers=hdr)))
    if cur.get("description") == DESC:
        print("repo_meta: description current"); return 0
    req = urllib.request.Request("https://api.github.com/repos/" + REPO, method="PATCH", headers=hdr,
                                 data=json.dumps({"description": DESC}).encode())
    back = json.load(urllib.request.urlopen(req))
    assert back.get("description") == DESC, back.get("description")
    print("repo_meta: description updated ->", DESC[:80] + "...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
