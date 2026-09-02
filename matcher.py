#!/usr/bin/env python3
"""TM Watch matcher v2 — deterministic trademark-name similarity flagging.

Given two mark names, decide whether a watch service should FLAG the pair
for human review. Signals (any one fires => flag):
  1. identical      — normalized/squeezed strings equal
  2. containment    — one dedoubled squeezed mark inside the other (len>=5),
                      or one mark's entire text appearing as a token of the other
  3. edit           — Damerau-Levenshtein similarity >= 0.80 (or dist<=1 for
                      short marks len<=4)
  4. phonetic       — metaphone-lite codes equal, or within DL distance 1
                      with string-similarity backup >= 0.45
  5. tokens         — >= 2/3 of the smaller mark's distinctive tokens match
                      the other mark's tokens (exact, plural-stripped, or
                      phonetic-equal)
  6. rare-token     — (v2, c76) the two marks share ONE distinctive token
                      (len >= 4, exact or plural-stripped — NOT phonetic) that is RARE in the
                      live Gazette corpus: not in common-tokens.json
                      (gen_rarity.py, df >= 10 over ~200k marks). Catches
                      VEUVE ROYALE / VEUVE CLICQUOT and GASPAR'S ALE / JOSE
                      GASPAR GOLD (the two v1 benchmark misses) while
                      PACIFIC / IRON / DENTAL / NORTH (common) stay silent.
                      If common-tokens.json is absent the rule is OFF
                      (compare() then behaves exactly like v1).

Deterministic, stdlib-only, no network. NOT legal advice: flags mean
"a human should look", never "confusingly similar" in the s.2(d) sense.

CLI: python3 matcher.py "MARK ONE" "MARK TWO"   -> prints verdict + reasons
"""

import json
import os
import re
import sys

STOPWORDS = {
    "THE", "AND", "OF", "FOR", "A", "AN", "BY", "CO", "INC", "LLC", "LLP",
    "CORP", "LTD", "USA", "GROUP", "SYSTEMS", "SYSTEM", "SOLUTIONS",
    "SERVICES", "SERVICE", "TECHNOLOGIES", "TECHNOLOGY", "TECH", "GLOBAL",
    "INTERNATIONAL", "BRANDS", "BRAND", "COMPANY", "PRODUCTS", "PRODUCT",
    "LABS", "LAB", "STUDIO", "STUDIOS", "ONLINE", "SHOP", "STORE",
}


def normalize(s: str) -> str:
    """Uppercase, unify separators/punctuation, collapse whitespace."""
    s = s.upper()
    s = s.replace("&", " AND ").replace("+", " PLUS ")
    s = re.sub(r"['’]", "", s)          # apostrophes vanish (BIGG'S->BIGGS)
    s = re.sub(r"[^A-Z0-9]+", " ", s)         # hyphens/dots/etc -> space
    return re.sub(r"\s+", " ", s).strip()


def squeeze(s: str) -> str:
    return s.replace(" ", "")


def dedouble(s: str) -> str:
    out = []
    for ch in s:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)


def dl_distance(a: str, b: str) -> int:
    """Damerau-Levenshtein (optimal string alignment) distance."""
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def dl_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    m = max(len(a), len(b))
    return 1.0 - dl_distance(a, b) / m if m else 0.0


VOWELS = set("AEIOUY")


def metaphone_lite(s: str) -> str:
    """Simplified deterministic phonetic code (metaphone-flavored).

    Works on a squeezed normalized string. Digits pass through.
    """
    s = squeeze(s)
    if not s:
        return ""
    # digraphs first
    s = s.replace("PH", "F").replace("GH", "K").replace("CK", "K")
    s = s.replace("SCH", "SK").replace("SH", "X").replace("CH", "X")
    s = s.replace("TH", "T").replace("WH", "W")
    out = []
    for i, ch in enumerate(s):
        if ch.isdigit():
            out.append(ch)
            continue
        if ch in VOWELS:
            if i == 0:
                out.append("A")   # initial vowel kept as A
            continue              # non-initial vowels dropped
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if ch == "C":
            out.append("S" if (nxt and nxt in "EIY") else "K")
        elif ch == "G":
            out.append("J" if (nxt and nxt in "EIY") else "K")
        elif ch == "Q":
            out.append("K")
        elif ch == "Z":
            out.append("S")
        elif ch == "V":
            out.append("F")
        elif ch == "X":
            out.append("KS")
        elif ch in ("W", "H"):
            continue
        else:
            out.append(ch)
    return dedouble("".join(out))


def _strip_plural(tok: str) -> str:
    if len(tok) > 3 and tok.endswith("S") and not tok.endswith("SS"):
        return tok[:-1]
    return tok


COMMON_TOKENS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "common-tokens.json")
_COMMON = None          # frozenset of common tokens, or None = rule 6 disabled
_COMMON_LOADED = False
RARE_MIN_LEN = 4


def set_common_tokens(tokens):
    """Install the common-token set (iterable of str) or None to disable rule 6."""
    global _COMMON, _COMMON_LOADED
    _COMMON = frozenset(tokens) if tokens is not None else None
    _COMMON_LOADED = True


def common_tokens():
    """Lazy-load common-tokens.json next to this file (once)."""
    global _COMMON_LOADED
    if not _COMMON_LOADED:
        _COMMON_LOADED = True
        if os.path.exists(COMMON_TOKENS_FILE):
            with open(COMMON_TOKENS_FILE) as f:
                set_common_tokens(json.load(f)["tokens"])
    return _COMMON


def _is_rare(tok: str) -> bool:
    """tok is a plural-stripped distinctive token. Rare = not in the common set."""
    common = common_tokens()
    return common is not None and len(tok) >= RARE_MIN_LEN and tok not in common


def _tokens(norm: str):
    return [t for t in norm.split(" ") if t]


def _distinctive(tokens):
    return [t for t in tokens if t not in STOPWORDS]


def _token_match(t1: str, t2: str) -> bool:
    if t1 == t2:
        return True
    if _strip_plural(t1) == _strip_plural(t2):
        return True
    if len(t1) >= 3 and len(t2) >= 3 and metaphone_lite(t1) == metaphone_lite(t2):
        return True
    return False


def compare(name1: str, name2: str):
    """Return (flag: bool, reasons: list[str], detail: dict)."""
    n1, n2 = normalize(name1), normalize(name2)
    s1, s2 = squeeze(n1), squeeze(n2)
    reasons = []

    # 1. identical after normalization
    if s1 and s1 == s2:
        reasons.append("identical")

    # 2. containment
    d1, d2 = dedouble(s1), dedouble(s2)
    small, big = (d1, d2) if len(d1) <= len(d2) else (d2, d1)
    if len(small) >= 5 and small in big and small != big:
        reasons.append("containment")
    else:
        # whole-mark-as-token: the entire shorter mark appears as a token
        toks1, toks2 = _tokens(n1), _tokens(n2)
        if len(s1) <= len(s2) and len(toks1) == 1 and s1 in toks2:
            reasons.append("whole-mark-token")
        elif len(s2) < len(s1) and len(toks2) == 1 and s2 in toks1:
            reasons.append("whole-mark-token")

    # 3. edit distance on squeezed strings
    sim = dl_similarity(s1, s2)
    dist = dl_distance(s1, s2)
    if s1 and s2:
        if max(len(s1), len(s2)) <= 4 and dist <= 1:
            reasons.append(f"edit-short(dist={dist})")
        elif sim >= 0.80:
            reasons.append(f"edit(sim={sim:.2f})")

    # 4. phonetic
    p1, p2 = metaphone_lite(n1), metaphone_lite(n2)
    if p1 and p2 and min(len(p1), len(p2)) >= 2:
        pdist = dl_distance(p1, p2)
        if p1 == p2:
            reasons.append(f"phonetic-equal({p1})")
        elif pdist == 1 and sim >= 0.45:
            reasons.append(f"phonetic-near({p1}~{p2},sim={sim:.2f})")

    # 5. token overlap
    t1 = _distinctive(_tokens(n1))
    t2 = _distinctive(_tokens(n2))
    if t1 and t2 and (len(t1) > 1 or len(t2) > 1):
        smaller, larger = (t1, t2) if len(t1) <= len(t2) else (t2, t1)
        matched = sum(1 for a in smaller if any(_token_match(a, b) for b in larger))
        ratio = matched / len(smaller)
        if matched >= 1 and ratio >= 0.67:
            reasons.append(f"tokens({matched}/{len(smaller)})")

        # 6. rare shared token (v2): an EXACT (or plural-stripped) shared token
        #    that is rare in the corpus. Phonetic token equality is deliberately
        #    NOT used here: metaphone-lite codes are short (VEUVE -> "F") and
        #    would match FAFO/VIVI/WAVY — measured +112 junk hits on the live
        #    corpus for "Veuve Royale" (c76). Exact-only measured +0..+11 per
        #    query, all sharing the actual rare word (KODIAK, NORTHSTAR).
        rare = None
        for a in smaller:
            sa = _strip_plural(a)
            if not _is_rare(sa):
                continue
            for b in larger:
                if _strip_plural(b) == sa:
                    rare = sa
                    break
            if rare:
                break
        if rare:
            reasons.append(f"rare-token({rare})")

    detail = {"norm1": n1, "norm2": n2, "phon1": p1, "phon2": p2,
              "edit_sim": round(sim, 3)}
    return (len(reasons) > 0, reasons, detail)


def main(argv):
    if len(argv) != 3:
        print("usage: matcher.py 'MARK ONE' 'MARK TWO'")
        return 2
    flag, reasons, detail = compare(argv[1], argv[2])
    print(f"flag={flag} reasons={','.join(reasons) or '-'} detail={detail}")
    return 0 if flag else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
