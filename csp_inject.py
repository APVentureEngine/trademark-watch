#!/usr/bin/env python3
"""Content-Security-Policy for a GitHub Pages site (c108).

GitHub Pages cannot set response headers, so the only CSP we can ship is the
<meta http-equiv> form. Both sites are fully self-contained (verified c108:
no external <script>/<img>/<link>/<iframe> in any generated page, every
fetch() is relative, no javascript: URLs, forms are JS-only), so a policy of
"self only" costs nothing and stops any injected/third-party script or
image from loading. 'unsafe-inline' is required because every page carries
inline <script>/<style>/onclick; that is the honest limit of a static site.

Why a post-processor and not a template edit: the two sites have 16+
hand-typed <head> templates across 10 generators. A hand-maintained anchor
list is exactly what rotted in c105; this walks the OUTPUT tree instead, so a
new generator is covered automatically and --check fails the publish if any
HTML file is missing the tag.

Usage (cwd-independent):
    python3 csp_inject.py <site_dir>            # inject (idempotent)
    python3 csp_inject.py <site_dir> --check    # exit 1 if any page lacks it
    python3 csp_inject.py --selftest
"""
import os
import re
import sys

POLICY = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
          "style-src 'self' 'unsafe-inline'; img-src 'self' data: https://cdn.jsdelivr.net; "
          "connect-src 'self'; font-src 'self'; object-src 'none'; "
          "base-uri 'self'; form-action 'self'; "
          "upgrade-insecure-requests")
TAG = '<meta http-equiv="Content-Security-Policy" content="%s">' % POLICY
_OLD = re.compile(r'\n?<meta http-equiv="Content-Security-Policy"[^>]*>\n?', re.I)
_CHARSET = re.compile(r'(<meta charset=["\']?utf-8["\']?>)', re.I)
_HEAD = re.compile(r'(<head>)', re.I)
SKIP_DIRS = {".git", "node_modules"}


def inject(html):
    """Return (new_html, changed). Places the tag right after <meta charset>
    (CSP must precede any resource load) or, failing that, after <head>."""
    stripped = _OLD.sub("", html)
    ins = "\n" + TAG + "\n"
    if _CHARSET.search(stripped):
        out = _CHARSET.sub(lambda m: m.group(1) + ins, stripped, count=1)
    elif _HEAD.search(stripped):
        out = _HEAD.sub(lambda m: m.group(1) + ins, stripped, count=1)
    else:
        return html, False          # not a page (fragment); leave alone
    return out, out != html


def walk(site):
    for dp, dns, fns in os.walk(site):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if fn.endswith(".html"):
                yield os.path.join(dp, fn)


def run(site, check=False):
    n = changed = missing = 0
    for p in walk(site):
        n += 1
        s = open(p, encoding="utf-8").read()
        if check:
            if TAG not in s:
                missing += 1
                if missing <= 5:
                    print("CSP MISSING: " + os.path.relpath(p, site))
            continue
        out, ch = inject(s)
        if ch:
            open(p, "w", encoding="utf-8").write(out)
            changed += 1
        if TAG not in out:
            missing += 1
    if check:
        print("csp check: %d page(s), %d missing" % (n, missing))
        return 1 if missing else 0
    print("csp inject: %d page(s), %d changed, %d without <head>" % (n, changed, missing))
    return 1 if missing else 0


def selftest():
    a = '<!doctype html><html><head><meta charset="utf-8">\n<title>x</title></head><body></body></html>'
    out, ch = inject(a)
    assert ch and out.count(TAG) == 1 and out.index(TAG) < out.index("<title>"), out
    out2, ch2 = inject(out)
    assert not ch2 and out2 == out, "not idempotent"
    stale = out.replace(POLICY, "default-src 'none'")
    out3, ch3 = inject(stale)
    assert ch3 and out3.count("Content-Security-Policy") == 1 and POLICY in out3, "old policy not replaced"
    b = "<html><head>\n<title>y</title></head></html>"
    out4, ch4 = inject(b)
    assert ch4 and out4.count(TAG) == 1
    for c0 in ("<head>\n<meta charset=utf-8>\n<title>z</title></head>",
               "<head><meta charset='UTF-8'><title>z</title></head>",
               "<head>\n<title>z</title></head>"):
        o1, _ = inject(c0); o2, ch = inject(o1)
        assert not ch and o1 == o2 and o1.count(TAG) == 1, (c0, o1)
    frag = "<p>no head</p>"
    assert inject(frag) == (frag, False)
    assert "'unsafe-inline'" in POLICY and "frame-ancestors" not in POLICY  # meta CSP ignores frame-ancestors
    print("csp_inject selftest: OK")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    sys.exit(run(args[0], check="--check" in sys.argv))
