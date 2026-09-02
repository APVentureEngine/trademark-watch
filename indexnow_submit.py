#!/usr/bin/env python3
"""Submit all sitemap URLs to IndexNow (Bing/Seznam/Naver/Yandex). Copied from
warn-feed (proven 200 there). Key file is public by spec: repo/<key>.txt served
on Pages; local copy indexnow_key.txt. Google ignores IndexNow — it reads
sitemap.xml via robots.txt. Run only when the URL set changed (sitemap diff).
200/202 accepted; 403 SiteVerificationNotCompleted = key file too new, retry
next run; 429 = slow down."""
import json, os, re, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://apventureengine.github.io/trademark-watch/"
key = open(os.path.join(HERE, "indexnow_key.txt")).read().strip()
urls = re.findall(r"<loc>(.*?)</loc>", open(os.path.join(HERE, "repo", "sitemap.xml")).read())
body = json.dumps({"host": "apventureengine.github.io", "key": key,
                   "keyLocation": BASE + key + ".txt", "urlList": urls}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                             headers={"Content-Type": "application/json; charset=utf-8"})
try:
    r = urllib.request.urlopen(req, timeout=30)
    print("IndexNow: %s for %d urls" % (r.status, len(urls)))
except urllib.error.HTTPError as e:
    print("IndexNow HTTP %s: %s" % (e.code, e.read()[:200]))
