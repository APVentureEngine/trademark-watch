#!/usr/bin/env python3
"""TM Watch paid fulfillment: Gumroad sale -> watchlist.json entry the weekly
watch runner matches against new Gazette filings, plus delivery setup:
  (a) EMAIL (primary, c73): alerts go to the purchaser's Gumroad email via
      mailer.py (Brevo). A welcome email confirms what happens next. If the
      mailer is not configured yet (A014 open) the entry is still recorded and
      the sale is flagged in needs_attention so nothing is silently lost.
  (b) GitHub private repo invite (secondary/optional): if the buyer gave a
      valid GitHub username, invite -> APVentureEngine/tm-watch-alerts.

Custom fields on product yqoJ16p67-UfQ1hnOtExvQ== ($49/yr, 1 mark):
  "Trademark to watch (exact text of your mark)"   required
  "GitHub username ..."                            optional once email is live
watchlist.json: sale_id -> {mark, email, user|null, start, expires(+365d)}.
Expiry enforcement is the runner's job; fulfill only records dates.

Idempotent via fulfilled.json. Failures -> needs_attention.json + loud
FULFILL-ATTENTION lines. Refunded sales skipped. v1: no access revocation on
refund (manual, same policy as warn-feed).

Usage: python3 fulfill.py [--dry-run] [--selftest]
Env: GUMROAD_ACCESS_TOKEN, GITHUB_ORG_TOKEN (+ BREVO_* for email). Never
prints tokens.
LESSON c65: unit selftest proves the component — refresh.sh must live-fire
this and its "fulfill:" summary line must appear in refresh stdout.
"""
import json, os, re, sys, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mailer  # noqa: E402

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
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SITE = "https://apventureengine.github.io/trademark-watch/"


def extract_email(sale):
    v = str((sale or {}).get("email") or "").strip().lower()
    return v if EMAIL_RE.match(v) and len(v) <= 254 else None


def welcome_message(mark, expires, user):
    repo_line = ("Your GitHub user %s has also been invited to the private alert-history "
                 "repo github.com/%s/%s.\n" % (user, OWNER, ALERTS_REPO)) if user else ""
    text = ("Your TM Watch is active.\n\n"
            "Watched mark: %s\nActive until: %s (one-time payment; we email a reminder "
            "two weeks before expiry)\n\n"
            "Every Tuesday the USPTO publishes the Trademark Official Gazette. The same "
            "day we run your mark against every newly published and newly registered "
            "word mark (name + phonetic + common-variant forms). If anything similar "
            "appears you get an email at this address listing serial, mark, Gazette "
            "date, classes, why it was flagged, and the USPTO TSDR status link. "
            "A published mark can be opposed (or an extension requested) for 30 days "
            "from its Gazette date.\n\n"
            "Quiet weeks mean no email. %s"
            "Refund: full refund within 14 days of purchase via Gumroad.\n"
            % (mark, expires, repo_line))
    return "TM Watch is active for %s" % mark, text



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
    cases_email = [
        ({"email": "Buyer@Example.com"}, "buyer@example.com"),
        ({"email": " x@y.zz "}, "x@y.zz"),
        ({"email": "nope"}, None), ({"email": ""}, None), ({}, None), (None, None),
    ]
    ok = True
    for sale, want in cases_email:
        got = extract_email(sale)
        if got != want:
            ok = False; print("SELFTEST FAIL email: %r -> %r (want %r)" % (sale, got, want))
    subj, body = welcome_message("ACME", "2027-09-01", None)
    assert "ACME" in subj and "2027-09-01" in body and "Tuesday" in body and "github.com" not in body
    subj, body = welcome_message("ACME", "2027-09-01", "octocat")
    assert "octocat" in body and ALERTS_REPO in body
    for cf, want in cases_user:
        got = extract_username(cf)
        if got != want:
            ok = False; print("SELFTEST FAIL user: %r -> %r (want %r)" % (cf, got, want))
    for cf, want in cases_mark:
        got = extract_mark(cf)
        if got != want:
            ok = False; print("SELFTEST FAIL mark: %r -> %r (want %r)" % (cf, got, want))
    print("selftest: %s (%d cases)" % ("PASS" if ok else "FAIL",
                                       len(cases_user) + len(cases_mark) + len(cases_email) + 2))
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
        email = extract_email(s)
        stamp = datetime.now(timezone.utc)
        ts = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        expires = (stamp + timedelta(days=365)).strftime("%Y-%m-%d")
        if not mark or not (email or user):
            attention[sid] = {"why": "missing mark text, or neither email nor username",
                              "raw": s.get("custom_fields"), "ts": ts}
            print("FULFILL-ATTENTION: sale %s: mark=%r email=%s user=%r unusable"
                  % (sid, mark, "yes" if email else "no", user))
            continue
        if dry:
            print("fulfill DRY-RUN: would watch %r for sale %s (email=%s, user=%r)"
                  % (mark, sid, "yes" if email else "no", user))
            continue
        delivery, problems = [], []
        # (b) optional private-repo invite
        if user:
            st, _ = api("https://api.github.com/users/" + urllib.parse.quote(user), token=gh)
            if st != 200:
                problems.append("github user %r not found (%s)" % (user, st))
                user = None
            else:
                st, body = api(
                    "https://api.github.com/repos/%s/%s/collaborators/%s"
                    % (OWNER, ALERTS_REPO, urllib.parse.quote(user)),
                    method="PUT", token=gh, body={"permission": "pull"},
                    accept="application/vnd.github+json")
                if st in (201, 204):
                    delivery.append("repo")
                else:
                    problems.append("invite failed status=%s msg=%s" % (st, body.get("message")))
                    user = None
        # (a) email welcome (primary channel)
        if email and mailer.configured():
            subj, text = welcome_message(mark, expires, user)
            ok, info = mailer.send(email, subj, text)
            if ok:
                delivery.append("email")
            else:
                problems.append("welcome email failed: " + info)
        elif email:
            problems.append("email delivery not configured yet (A014) — alerts held until it is")
        watchlist[sid] = {"mark": mark, "email": email, "user": user,
                          "start": ts, "expires": expires}
        fulfilled[sid] = {"status": "watching", "delivery": delivery, "ts": ts}
        n_new += 1
        if delivery:
            attention.pop(sid, None)
        else:
            attention[sid] = {"why": "NO LIVE DELIVERY CHANNEL: " + "; ".join(problems),
                              "user": user, "ts": ts}
        for pr in problems:
            print("FULFILL-ATTENTION: sale %s: %s" % (sid, pr))
        print("fulfill: watching %r for sale %s via %s" % (mark, sid, "+".join(delivery) or "NONE"))
    if not dry:
        save(FULFILLED, fulfilled)
        save(ATTENTION, attention)
        save(WATCHLIST, watchlist)
    print("fulfill: %d paid sales seen, %d newly fulfilled, %d watching, %d needing attention"
          % (n_seen, n_new, len(watchlist), len(attention)))
    sys.exit(0)


if __name__ == "__main__":
    main()
