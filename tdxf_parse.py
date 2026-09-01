#!/usr/bin/env python3
"""TDXF (Trademark Daily XML File, applications) parser -> mark records.

Target format: USPTO "trademark-applications-daily" DTD (v2.x, the format the
decommissioned bulkdata served and ODP's TRTDXFAP product serves today).
Written BEFORE first real file (A010 pending) against the public DTD docs, so
it is DEFENSIVE:
  - iterparse on end-of-<case-file>; all field reads tolerate absence
  - unknown structure never raises; records missing serial/mark/filing-date
    are counted + skipped, not fatal
  - `--probe file.xml[.zip]` prints a tag histogram + 3 sample records so the
    FIRST real-data run can be eyeballed for schema drift before trusting it
    (lesson: SPA-era USPTO surfaces lie; verify shape, not status codes).

Record (superset of gen_index.py input; extra keys are ignored downstream):
  {"serial": int, "mark": str, "filing_date": "YYYY-MM-DD",
   "classes": [int...], "pseudo": [str...], "status": str, "owner": str,
   "transaction_date": "YYYY-MM-DD"}

Stdlib only. Deterministic.
"""
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

DATE_RE = re.compile(r"^\d{8}$")


def _date(s):
    """YYYYMMDD -> YYYY-MM-DD, else None."""
    if s and DATE_RE.match(s.strip()):
        s = s.strip()
        return "%s-%s-%s" % (s[:4], s[4:6], s[6:8])
    return None


def _text(el, path):
    v = el.findtext(path)
    return v.strip() if v and v.strip() else None


def parse_case_file(cf):
    """One <case-file> element -> record dict or None (unusable)."""
    serial = _text(cf, "serial-number")
    try:
        serial = int(serial)
    except (TypeError, ValueError):
        return None
    hdr = cf.find("case-file-header")
    mark = _text(hdr, "mark-identification") if hdr is not None else None
    filing = _date(_text(hdr, "filing-date")) if hdr is not None else None
    if not mark or not filing:
        return None
    rec = {"serial": serial, "mark": mark, "filing_date": filing, "classes": []}
    status = _text(hdr, "status-code")
    if status:
        rec["status"] = status
    tx = _date(_text(cf, "transaction-date"))
    if tx:
        rec["transaction_date"] = tx
    # classifications: keep valid international classes 1..45 only
    for cl in cf.iter("classification"):
        code = _text(cl, "international-code")
        if code:
            try:
                n = int(code)
                if 1 <= n <= 45 and n not in rec["classes"]:
                    rec["classes"].append(n)
            except ValueError:
                pass  # "A"/"B"/"200" cert/collective marks — skip
    rec["classes"].sort()
    # pseudo marks: case-file-statement type-code PM*
    pseudo = []
    for st in cf.iter("case-file-statement"):
        tc = _text(st, "type-code") or ""
        if tc.upper().startswith("PM"):
            txt = _text(st, "text")
            if txt and txt not in pseudo:
                pseudo.append(txt)
    if pseudo:
        rec["pseudo"] = pseudo
    owner = None
    for ow in cf.iter("case-file-owner"):
        owner = _text(ow, "party-name") or owner
        break
    if owner:
        rec["owner"] = owner
    return rec


def _open_xml(path):
    """Path may be .xml or a .zip containing one+ xml members."""
    if path.lower().endswith(".zip"):
        zf = zipfile.ZipFile(path)
        names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
        if not names:
            raise RuntimeError("zip %s has no xml member" % path)
        return io.BytesIO(zf.read(names[0]))
    return open(path, "rb")


def parse_file(path):
    """Yield records from a TDXF xml/zip file. Never raises on bad case-files;
    returns (records, n_skipped) via generator protocol: caller counts."""
    skipped = 0
    with _open_xml(path) as f:
        for _ev, el in ET.iterparse(f, events=("end",)):
            tag = el.tag.rsplit("}", 1)[-1]  # tolerate a namespace if one appears
            if tag == "case-file":
                rec = parse_case_file(el)
                if rec is None:
                    skipped += 1
                else:
                    yield rec
                el.clear()
    if skipped:
        print("tdxf_parse: %d case-files skipped (no serial/mark/filing-date)"
              % skipped, file=sys.stderr)


def probe(path):
    """Schema-drift probe: tag histogram + first 3 parsed records."""
    from collections import Counter
    hist = Counter()
    with _open_xml(path) as f:
        for _ev, el in ET.iterparse(f, events=("end",)):
            hist[el.tag.rsplit("}", 1)[-1]] += 1
    print("=== tag histogram (top 40) ===")
    for tag, n in hist.most_common(40):
        print("%8d  %s" % (n, tag))
    print("=== first 3 records ===")
    for i, rec in enumerate(parse_file(path)):
        print(json.dumps(rec, sort_keys=True))
        if i >= 2:
            break
    if hist.get("case-file", 0) == 0:
        print("PROBE-WARNING: zero <case-file> elements — SCHEMA DRIFT, "
              "do not trust parser output until reconciled", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--probe":
        sys.exit(probe(sys.argv[2]))
    if len(sys.argv) >= 2:
        n = 0
        for rec in parse_file(sys.argv[1]):
            print(json.dumps(rec, sort_keys=True))
            n += 1
        print("tdxf_parse: %d records" % n, file=sys.stderr)
        sys.exit(0)
    print("usage: tdxf_parse.py [--probe] <file.xml|file.zip>", file=sys.stderr)
    sys.exit(2)
