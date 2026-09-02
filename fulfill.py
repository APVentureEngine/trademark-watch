#!/usr/bin/env python3
"""TM Watch paid fulfillment: Gumroad sale -> (a) private alerts-repo invite,
(b) watchlist.json entry the daily watch runner matches against new filings.

Adapted from warn-feed fulfill.py (proven live c65) with tm-watch deltas:
  - product yqoJ16p67-UfQ1hnOtExvQ== ($49/yr, 1 mark) -> APVentureEngine/tm-watch-alerts
  - TWO custom fields: "Trademark to watch (exact text of your mark)" and
    "GitHub username (for private alert repo access)" (both required at
    checkout; verified on the live unpublished product c66).
  - watchlist.json: sale_id -> {mark, user, start, expires(+365d)}. The watch
    runner (needs A010 data) reads this; expiry enforcement is the runner's
    job, fulfill only records dates.

Idempotent via fulfilled.json. Failures -> needs_attention.json + loud
FULFILL-ATTENTION lines. Refunded sales skipped. v1: no access revocation on
refund (manual, same policy as warn-feed).

Usage: python3 fulfill.py [--dry-run] [--selftest]
Env: GUMROAD_ACCESS_TOKEN, GITHUB_ORG_TOKEN. Never prints tokens.
LESSON c65: unit selftest proves the component — refresh.sh must live-fire
this and its "fulfill:" summary line must appear in refresh stdout.
"""
import json, os, re, sys, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
FULFILLED = os.path.join(HERE, "fulfilled.json")
ATTENTION = os.path.join(HERE, "needs_attention.json")
WATCHLIST = os.path.join(HERE, "watchlist.json")
OWNER = "APVentureEngine"
ALERTS_REPO = "tm-watch-alerts"
PRODUCT_IDS = {"yqoJ16p67-UfQ1hnOtExvQ=="}
GH_FIELD_HINT = "github"
MARK_FIELD_HINT = "trademark"
SALES_AFTER = "2026-09-01"
USER_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$")


def _pairs(custom_fields):
    if isinstance(custom_fields, dict):
        return [(str(k), str(v)) for k, v in custom_fields.items()]
    if isinstance(custom_fields, list):
        return [(str(cf.get("name", "")), str(cf.get("value", "")))
                for cf in custom_fields if isinstance(cf, dict)]
    return []


def extract_username(custom_fields):
    for name, value in _pairs(custom_fields):
        if GH_FIELD_HINT in name.lower():
            return sanitize_username(value)
    return None


def extract_mark(custom_fields):
    for name, value in _pairs(custom_fields):
        if MARK_FIELD_HINT in name.lower() or "mark" in name.lower().split():
            v = value.strip()
            return v if 0 < len(v) <= 120 else None
    return None


def sanitize_username(raw):
    v = raw.strip().strip(".,;")
    if "github.com" in v.lower():
        path = urllib.parse.urlparse(v if "//" in v else "//" + v).path
        segs = [s for s in path.split("/") if s]
        v = segs[0] if segs else ""
    v = v.lstrip("@").strip()
    return v if USER_RE.match(v) else None


def api(url, method="GET", token=None, body=None, accept=None):
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            txt = r.read().decode() or "{}"
            return r.status, (json.loads(txt) if txt.strip() else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return -1, {"error": type(e).__name__}


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def save(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")


def iter_sales(gr_token):
    url = ("https://api.gumroad.com/v2/sales?access_token="
           + urllib.parse.quote(gr_token) + "&after=" + SALES_AFTER)
    for _ in range(20):
        status, d = api(url)
        if status != 200 or not d.get("success", True):
            print("FULFILL-ATTENTION: gumroad sales fetch failed status=%s" % status)
            return
        for s in d.get("sales", []):
            yield s
        nxt = d.get("next_page_url")
        if not nxt:
            return
        url = "https://api.gumroad.com" + nxt + "&access_token=" + urllib.parse.quote(gr_token)


def selftest():
    F_GH = "GitHub username (for private alert repo access)"
    F_TM = "Trademark to watch (exact text of your mark)"
    cases_user = [
        ({F_GH: "octocat", F_TM: "ACME"}, "octocat"),
        ({F_GH: " @Octo-Cat "}, "Octo-Cat"),
        ({F_GH: "https://github.com/torvalds/"}, "torvalds"),
        ([{"name": F_GH, "value": "octocat"}, {"name": F_TM, "value": "ACME"}], "octocat"),
        ({F_GH: "not a user!!"}, None),
        ({F_GH: "-bad"}, None),
        ({F_TM: "ACME"}, None),
        ({}, None), (None, None),
    ]
    cases_mark = [
        ({F_TM: " Acme Robotics "}, "Acme Robotics"),
        ([{"name": F_TM, "value": "NYKE"}], "NYKE"),
        ({F_TM: ""}, None),
        ({F_TM: "x" * 121}, None),
        ({F_GH: "octocat"}, None),
        ({"Your mark text": "ZED"}, "ZED"),
        ({}, None), (None, None),
    ]
    ok = True
    for cf, want in cases_user:
        got = extract_username(cf)
        if got != want:
            ok = False; print("SELFTEST FAIL user: %r -> %r (want %r)" % (cf, got, want))
    for cf, want in cases_mark:
        got = extract_mark(cf)
        if got != want:
            ok = False; print("SELFTEST FAIL mark: %r -> %r (want %r)" % (cf, got, want))
    print("selftest: %s (%d cases)" % ("PASS" if ok else "FAIL",
                                       len(cases_user) + len(cases_mark)))
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    dry = "--dry-run" in sys.argv
    gr = os.environ.get("GUMROAD_ACCESS_TOKEN")
    gh = os.environ.get("GITHUB_ORG_TOKEN")
    if not gr or not gh:
        print("fulfill: missing GUMROAD_ACCESS_TOKEN or GITHUB_ORG_TOKEN in env")
        sys.exit(1)
    fulfilled = load(FULFILLED)
    attention = load(ATTENTION)
    watchlist = load(WATCHLIST)
    n_seen = n_new = 0
    for s in iter_sales(gr):
        if s.get("product_id") not in PRODUCT_IDS:
            continue
        n_seen += 1
        sid = str(s.get("id"))
        if sid in fulfilled:
            continue
        if s.get("refunded") or s.get("chargebacked") or s.get("chargedback"):
            fulfilled[sid] = {"status": "skipped_refunded"}
            continue
        user = extract_username(s.get("custom_fields"))
        mark = extract_mark(s.get("custom_fields"))
        stamp = datetime.now(timezone.utc)
        ts = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        if not user or not mark:
            attention[sid] = {"why": "missing username or mark text",
                              "raw": s.get("custom_fields"), "ts": ts}
            print("FULFILL-ATTENTION: sale %s: user=%r mark=%r unusable" % (sid, user, mark))
            continue
        st, _ = api("https://api.github.com/users/" + urllib.parse.quote(user), token=gh)
        if st != 200:
            attention[sid] = {"why": "github user not found (%s)" % st,
                              "user": user, "ts": ts}
            print("FULFILL-ATTENTION: sale %s: user %r not on GitHub (%s)" % (sid, user, st))
            continue
        if dry:
            print("fulfill DRY-RUN: would invite %s -> %s/%s and watch %r (sale %s)"
                  % (user, OWNER, ALERTS_REPO, mark, sid))
            continue
        st, body = api(
            "https://api.github.com/repos/%s/%s/collaborators/%s"
            % (OWNER, ALERTS_REPO, urllib.parse.quote(user)),
            method="PUT", token=gh, body={"permission": "pull"},
            accept="application/vnd.github+json")
        if st in (201, 204):
            watchlist[sid] = {"mark": mark, "user": user, "start": ts,
                              "expires": (stamp + timedelta(days=365)).strftime("%Y-%m-%d")}
            fulfilled[sid] = {"status": "invited" if st == 201 else "already_collaborator",
                              "user": user, "ts": ts}
            attention.pop(sid, None)
            n_new += 1
            print("fulfill: %s -> %s/%s, watching %r" % (user, OWNER, ALERTS_REPO, mark))
        else:
            attention[sid] = {"why": "invite failed status=%s msg=%s" % (st, body.get("message")),
                              "user": user, "ts": ts}
            print("FULFILL-ATTENTION: invite %s failed (%s)" % (user, st))
    if not dry:
        save(FULFILLED, fulfilled)
        save(ATTENTION, attention)
        save(WATCHLIST, watchlist)
    print("fulfill: %d paid sales seen, %d newly fulfilled, %d watching, %d needing attention"
          % (n_seen, n_new, len(watchlist), len(attention)))
    sys.exit(0)


if __name__ == "__main__":
    main()
