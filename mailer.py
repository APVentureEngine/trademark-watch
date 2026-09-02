#!/usr/bin/env python3
"""Transactional email for TM Watch alerts via Brevo (free tier, 300/day).

Why: the site review (2026-09-01, NOT_READY 48) named GitHub-only alert
delivery as the structural blocker — the SMB buyer has no GitHub account.
This module makes email the primary channel; the private repo stays as an
optional secondary (history/RSS for technical users).

Env (injected by the engine once inbox A014 lands; never printed):
  BREVO_API_KEY       Brevo v3 API key
  BREVO_SENDER_EMAIL  confirmed sender address (the "from")
  BREVO_SENDER_NAME   optional, default "TM Watch"

API: POST https://api.brevo.com/v3/smtp/email, header api-key, JSON body
{sender, to, subject, htmlContent, textContent}. 201 => {"messageId": ...}.

Usage:
  python3 mailer.py --selftest     no network: payload shape + configured()
  python3 mailer.py --live-test    sends ONE email to BREVO_SENDER_EMAIL and
                                   prints status (the A014 proof step)
Library:
  configured() -> bool
  send(to, subject, text, html=None) -> (ok: bool, info: str)
  Both callers (fulfill.py, watch_run.py) treat not-configured as "skip
  quietly and say so", never as an error — the repo path still works.
"""
import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SENDER_NAME_DEFAULT = "TM Watch"
FOOTER_TEXT = ("\n--\nTM Watch — automated similarity flags for human review. "
               "Not legal advice; no opinion on likelihood of confusion. "
               "Free check + methodology: https://apventureengine.github.io/trademark-watch/\n"
               "Reply to this email to reach the operator.\n")
FOOTER_HTML = ("<p style=\"color:#666;font-size:12px;margin-top:24px\">TM Watch — automated "
               "similarity flags for human review. Not legal advice; no opinion on "
               "likelihood of confusion. <a href=\"https://apventureengine.github.io/trademark-watch/\">"
               "Free check + methodology</a>. Reply to this email to reach the operator.</p>")


def configured():
    return bool(os.environ.get("BREVO_API_KEY")) and bool(os.environ.get("BREVO_SENDER_EMAIL"))


def build_payload(to, subject, text, html=None, sender_email="sender@example.invalid",
                  sender_name=SENDER_NAME_DEFAULT, reply_to=None):
    if not isinstance(to, str) or "@" not in to or len(to) > 254:
        raise ValueError("bad recipient")
    if not subject or len(subject) > 200:
        raise ValueError("bad subject")
    body = {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [{"email": to.strip()}],
        "replyTo": {"email": reply_to or sender_email},
        "subject": subject,
        "textContent": text + FOOTER_TEXT,
        "htmlContent": (html or "<pre>%s</pre>" % _esc(text)) + FOOTER_HTML,
        "tags": ["tm-watch"],
    }
    return body


def _esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def send(to, subject, text, html=None):
    """Returns (ok, info). Never raises on network/API failure; never prints the key."""
    if not configured():
        return False, "mailer not configured (BREVO_API_KEY/BREVO_SENDER_EMAIL absent)"
    try:
        payload = build_payload(to, subject, text, html,
                                sender_email=os.environ["BREVO_SENDER_EMAIL"],
                                sender_name=os.environ.get("BREVO_SENDER_NAME", SENDER_NAME_DEFAULT))
    except ValueError as e:
        return False, "invalid message: %s" % e
    req = urllib.request.Request(ENDPOINT, method="POST",
                                 data=json.dumps(payload).encode())
    req.add_header("api-key", os.environ["BREVO_API_KEY"])
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode() or "{}")
            return True, "sent messageId=%s" % d.get("messageId", "?")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode() or "{}").get("message", "")
        except Exception:
            msg = ""
        return False, "brevo http %s %s" % (e.code, msg[:200])
    except Exception as e:
        return False, "brevo error %s" % type(e).__name__


def selftest():
    p = build_payload("buyer@example.com", "TM Watch alert — ACME — 2026-09-02",
                      "1 similar mark\nACMEE serial 90000001", "<b>ACMEE</b>")
    assert p["to"] == [{"email": "buyer@example.com"}]
    assert p["textContent"].startswith("1 similar mark") and "Not legal advice" in p["textContent"]
    assert p["htmlContent"].startswith("<b>ACMEE</b>") and "Not legal advice" in p["htmlContent"]
    assert p["replyTo"]["email"] == "sender@example.invalid"
    for bad in ["nope", "", None, "a" * 300 + "@x.y"]:
        try:
            build_payload(bad, "s", "t")
            raise AssertionError("accepted bad recipient %r" % (bad,))
        except ValueError:
            pass
    # unconfigured send must be a quiet skip, not an exception
    saved = {k: os.environ.pop(k, None) for k in ("BREVO_API_KEY", "BREVO_SENDER_EMAIL")}
    try:
        ok, info = send("buyer@example.com", "x", "y")
        assert not ok and "not configured" in info, info
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
    print("mailer selftest: PASS (payload, footer rails, recipient validation, "
          "unconfigured=skip; configured now=%s)" % configured())
    return 0


def live_test():
    if not configured():
        print("mailer live-test: NOT configured (A014 not landed) — skipped")
        return 2
    to = os.environ["BREVO_SENDER_EMAIL"]
    ok, info = send(to, "TM Watch — email delivery is live (test)",
                    "This is the one-time test email proving TM Watch can send alerts.\n"
                    "Nothing to do.")
    print("mailer live-test: %s — %s" % ("OK" if ok else "FAIL", info))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    if "--live-test" in sys.argv:
        sys.exit(live_test())
    print(__doc__)
