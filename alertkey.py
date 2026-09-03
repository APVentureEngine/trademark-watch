#!/usr/bin/env python3
"""TM Watch — the ONE place the private alert-page ADDRESS and the wording that
explains it are defined. Import from here; never retype either.

Why this module exists (c107, 2026-09-03)
-----------------------------------------
Until now the address was  sha256("tmwatch|" + MARK + "|" + email)[:32].
Both inputs are things a third party can KNOW: a trademark is public by
definition (that is the whole product), and a work email is guessable. So any
rival who knew "Kodiak Coffee watches its mark, and Sam's address is
sam@kodiak.com" could compute Sam's unlisted page and read what Sam is being
warned about. warn-feed hit the identical defect in c106 and fixed it the same
way; this is that fix ported before TM Watch's first sale (watchlist was empty
on 2026-09-03, so there was no migration).

The address is now derived from something only the BUYER CHOSE:

    slug = sha256("tmwatch|" + MARK + "|" + email + "|" + passphrase)[:32]

    MARK       upper-cased, whitespace collapsed, trimmed      (norm_mark)
    email      lower-cased, trimmed                            (norm_email)
    passphrase lower-cased, trimmed, whitespace collapsed;     (passphrase_key)
               punctuation KEPT so a buyer can retype exactly what they typed

The passphrase is a REQUIRED custom field on BOTH Gumroad listings (paid
yqoJ16p67-UfQ1hnOtExvQ==, free DXbAI_1fRuKYAp8J7GUz0Q==), created via
POST /v2/products/<id>/custom_fields on 2026-09-03. A sale that somehow has no
passphrase falls back to key="" and prints FULFILL-ATTENTION — that is a
defensive path, never a documented one.

Parity rule: the finder page (site/alerts/index.html, JS in gen_alert_pages.py)
computes the SAME string in the browser. Any change to normalisation here must
change the JS in the same commit; gen_alert_pages --selftest checks both under
quickjs and fails if they drift.

Stdlib only. `python3 alertkey.py --selftest` is a publish gate.
"""
import hashlib
import re
import sys

SITE = "https://apventureengine.github.io/trademark-watch/"

# The exact Gumroad checkout field (live on both listings since 2026-09-03).
PASSPHRASE_FIELD = ("Passphrase (required) — any word or short phrase; you type it "
                    "with your mark and email to open your alert page")
PASSPHRASE_HINT = "passphrase"          # substring match against sale custom-field names

# ONE wording for every surface that explains how to open the page: receipts,
# Gumroad descriptions, the PDFs, the landing page, the alert page itself.
HOWTO_SHORT = ("type your mark, the email you used at checkout, and the passphrase you chose "
               "in the checkout box")
HOWTO_LONG = ("open " + SITE + "alerts/ and type your mark exactly as you entered it, the email address "
              "you used at checkout, and the passphrase you chose in the checkout box. Your browser works "
              "out the private address locally from those three (SHA-256, nothing is sent anywhere). "
              "Because the passphrase is yours alone, nobody who merely knows your trademark and your "
              "email address can open your page.")
# Shown next to the finder form and on the alert page; explains the fallback
# without advertising it as a route.
NO_PASSPHRASE_NOTE = ("Bought before the passphrase box existed (no passphrase at your checkout)? "
                      "Leave the passphrase field empty.")


def norm_mark(m):
    return " ".join(str(m).upper().split())


def norm_email(e):
    return str(e).strip().lower()


def passphrase_key(raw):
    """Normalise the checkout passphrase exactly like the finder JS: lowercase,
    trim, collapse runs of whitespace to one space. Punctuation is KEPT."""
    return re.sub(r"\s+", " ", str(raw or "").strip().lower())


def slug(mark, email, key=""):
    s = "tmwatch|%s|%s|%s" % (norm_mark(mark), norm_email(email), passphrase_key(key))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:32]


def sale_passphrase(custom_fields):
    """Pull the passphrase out of a Gumroad sale's custom fields (dict or list
    shape). Returns the normalised key, or "" when the buyer has none."""
    pairs = []
    if isinstance(custom_fields, dict):
        pairs = [(str(k), str(v)) for k, v in custom_fields.items()]
    elif isinstance(custom_fields, list):
        pairs = [(str(cf.get("name", "")), str(cf.get("value", "")))
                 for cf in custom_fields if isinstance(cf, dict)]
    for name, value in pairs:
        if PASSPHRASE_HINT in name.lower():
            return passphrase_key(value)
    return ""


def selftest():
    # normalisation
    assert passphrase_key("  Blue   Moon-42! ") == "blue moon-42!"
    assert passphrase_key(None) == "" and passphrase_key("") == ""
    assert norm_mark(" kodiak  coffee ") == "KODIAK COFFEE"
    assert norm_email(" A@B.com ") == "a@b.com"
    # the three inputs all matter, and case/space noise does not
    a = slug("Kodiak Coffee", "a@b.com", "blue moon")
    assert a == slug(" kodiak   coffee ", " A@B.COM ", "  Blue  Moon ")
    assert a != slug("Kodiak Coffee", "a@b.com", "other")     # passphrase matters
    assert a != slug("Kodiak Coffee", "c@b.com", "blue moon")  # email matters
    assert a != slug("Kodiak Brew", "a@b.com", "blue moon")    # mark matters
    assert len(a) == 32 and a == hashlib.sha256(
        b"tmwatch|KODIAK COFFEE|a@b.com|blue moon").hexdigest()[:32]
    # the pre-passphrase address must NOT be reachable any more
    legacy = hashlib.sha256(b"tmwatch|KODIAK COFFEE|a@b.com").hexdigest()[:32]
    assert slug("Kodiak Coffee", "a@b.com") != legacy
    # sale custom-field extraction, both API shapes
    assert sale_passphrase([{"name": PASSPHRASE_FIELD, "value": " Blue Moon "}]) == "blue moon"
    assert sale_passphrase({PASSPHRASE_FIELD: "Zeta"}) == "zeta"
    assert sale_passphrase([{"name": "Trademark to watch", "value": "KODIAK"}]) == ""
    assert sale_passphrase(None) == ""
    # copy surfaces say passphrase and never promise email delivery here
    for t in (HOWTO_SHORT, HOWTO_LONG):
        assert "passphrase" in t.lower()
    assert SITE + "alerts/" in HOWTO_LONG
    print("alertkey selftest PASS")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else selftest())
