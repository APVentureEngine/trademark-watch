#!/usr/bin/env python3
"""Trademark Official Gazette (TMOG) weekly ST.96 XML -> mark records.

Data path (c72, replaces the ODP key that the partner can never obtain):
  https://cdn.uspto.gov/doc/TMOGIssue_YYYYMMDD_entire?extension=xml
  (302 -> Google Cloud Storage, ~230MB, NO API key, public-domain USPTO data).
  Issues publish every Tuesday; the list of issue dates is public at
  https://tm-eog-service.uspto.gov/eog-rest-service/api/external/search/publications

The gazette is WIPO ST.96 XML: one <tmk:Trademark> per published event.
Sections we keep (PublicationSectionCategory):
  "Applications publishing for opposition" -> event "published"
      (the 30-day opposition window opens on the issue date — THE alert)
  "Registrations publishing"               -> event "registered"
Everything else (cancellations, renewals, corrections) is skipped: a watch is
about marks that are ARRIVING, not leaving.

Record (superset of gen_index.py input; extra keys ignored downstream):
  {"serial": int, "mark": str, "filing_date": "YYYY-MM-DD",
   "pub_date": "YYYY-MM-DD", "event": "published"|"registered",
   "classes": [int...], "owner": str, "status": str,
   "reg_num": str|None, "transaction_date": pub_date}
Marks with no verbal element (pure design marks) are counted + skipped:
the matcher is text-only and the site says so.

Stdlib only. Deterministic. `--probe file.xml` prints section histogram +
3 sample records so schema drift is eyeballed before it is trusted.
"""
import json
import sys
import xml.etree.ElementTree as ET

T = "{http://www.wipo.int/standards/XMLSchema/Trademark/1}"
C = "{http://www.wipo.int/standards/XMLSchema/Common/1}"

KEEP = {
    "Applications publishing for opposition": "published",
    "Registrations publishing": "registered",
}


def _t(el, path):
    v = el.findtext(path)
    return v.strip() if v and v.strip() else None


def _date(s):
    # ST.96 dates look like 2026-03-27-04:00 (date + TZ offset) or 2026-09-01
    if s and len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def parse_trademark(el):
    """One <tmk:Trademark> -> (record|None, skip_reason|None)."""
    section = _t(el, ".//" + T + "PublicationSectionCategory")
    event = KEEP.get(section or "")
    if not event:
        return None, "section"
    serial = _t(el, ".//" + C + "ApplicationNumberText")
    try:
        serial = int(serial)
    except (TypeError, ValueError):
        return None, "serial"
    mark = _t(el, ".//" + T + "MarkSignificantVerbalElementText")
    if not mark:
        return None, "design-only"
    filing = _date(_t(el, T + "ApplicationDate"))
    pub = _date(_t(el, ".//" + C + "PublicationDate"))
    if not pub:
        return None, "pub-date"
    rec = {"serial": serial, "mark": mark, "filing_date": filing or pub,
           "pub_date": pub, "event": event, "classes": [],
           "transaction_date": pub}
    for gc in el.iter(T + "GoodsServicesClassification"):
        if _t(gc, T + "ClassificationKindCode") == "Nice":
            try:
                n = int(_t(gc, T + "ClassNumber") or "")
                if 1 <= n <= 45 and n not in rec["classes"]:
                    rec["classes"].append(n)
            except ValueError:
                pass
    rec["classes"].sort()
    owner = (_t(el, ".//" + C + "OrganizationStandardName")
             or _t(el, ".//" + C + "PersonFullName")
             or _t(el, ".//" + C + "EntityName"))
    if owner:
        rec["owner"] = owner
    status = _t(el, T + "MarkCurrentStatusCode")
    if status:
        rec["status"] = status
    reg = _t(el, ".//" + C + "RegistrationNumber")
    if reg:
        rec["reg_num"] = reg
    return rec, None


def parse_file(path, stats=None):
    """Yield records from a TMOG issue XML. stats (dict) gets skip counts."""
    stats = stats if stats is not None else {}
    for _ev, el in ET.iterparse(path, events=("end",)):
        if el.tag == T + "Trademark":
            rec, why = parse_trademark(el)
            if rec:
                stats["kept"] = stats.get("kept", 0) + 1
                yield rec
            else:
                stats[why] = stats.get(why, 0) + 1
            el.clear()


def probe(path):
    stats = {}
    samples = []
    for rec in parse_file(path, stats):
        if len(samples) < 3 and len(samples) < 3:
            samples.append(rec)
    print(json.dumps(stats, indent=1, sort_keys=True))
    for s in samples:
        print(json.dumps(s, sort_keys=True))


def selftest():
    xml = ("<tmk:Transaction xmlns:tmk='http://www.wipo.int/standards/XMLSchema/Trademark/1' "
           "xmlns:com='http://www.wipo.int/standards/XMLSchema/Common/1'>"
           "<tmk:Trademark><com:ApplicationNumber><com:ApplicationNumberText>99000001</com:ApplicationNumberText></com:ApplicationNumber>"
           "<tmk:ApplicationDate>2026-03-27-04:00</tmk:ApplicationDate><tmk:MarkCurrentStatusCode>681</tmk:MarkCurrentStatusCode>"
           "<tmk:MarkRepresentation><tmk:MarkReproduction><tmk:WordMarkSpecification><tmk:MarkSignificantVerbalElementText>ACME ROCKET</tmk:MarkSignificantVerbalElementText></tmk:WordMarkSpecification></tmk:MarkReproduction></tmk:MarkRepresentation>"
           "<tmk:GoodsServicesBag><tmk:GoodsServices><tmk:GoodsServicesClassificationBag>"
           "<tmk:GoodsServicesClassification><tmk:ClassificationKindCode>Primary</tmk:ClassificationKindCode><tmk:ClassNumber>9</tmk:ClassNumber></tmk:GoodsServicesClassification>"
           "<tmk:GoodsServicesClassification><tmk:ClassificationKindCode>Nice</tmk:ClassificationKindCode><tmk:ClassNumber>9</tmk:ClassNumber></tmk:GoodsServicesClassification>"
           "<tmk:GoodsServicesClassification><tmk:ClassificationKindCode>Nice</tmk:ClassificationKindCode><tmk:ClassNumber>42</tmk:ClassNumber></tmk:GoodsServicesClassification>"
           "<tmk:GoodsServicesClassification><tmk:ClassificationKindCode>National</tmk:ClassificationKindCode><tmk:NationalClassNumber>100</tmk:NationalClassNumber></tmk:GoodsServicesClassification>"
           "</tmk:GoodsServicesClassificationBag></tmk:GoodsServices></tmk:GoodsServicesBag>"
           "<tmk:PublicationBag><tmk:Publication><tmk:PublicationSectionCategory>Applications publishing for opposition</tmk:PublicationSectionCategory><com:PublicationDate>2026-09-01</com:PublicationDate></tmk:Publication></tmk:PublicationBag>"
           "<tmk:ApplicantBag><tmk:Applicant><com:Contact><com:Name><com:OrganizationName><com:OrganizationStandardName>Acme Corp</com:OrganizationStandardName></com:OrganizationName></com:Name></com:Contact></tmk:Applicant></tmk:ApplicantBag>"
           "</tmk:Trademark>"
           # design-only (no verbal element) -> skipped
           "<tmk:Trademark><com:ApplicationNumber><com:ApplicationNumberText>99000002</com:ApplicationNumberText></com:ApplicationNumber>"
           "<tmk:PublicationBag><tmk:Publication><tmk:PublicationSectionCategory>Applications publishing for opposition</tmk:PublicationSectionCategory><com:PublicationDate>2026-09-01</com:PublicationDate></tmk:Publication></tmk:PublicationBag></tmk:Trademark>"
           # cancellation -> skipped by section
           "<tmk:Trademark><com:ApplicationNumber><com:ApplicationNumberText>99000003</com:ApplicationNumberText></com:ApplicationNumber>"
           "<tmk:MarkRepresentation><tmk:MarkReproduction><tmk:WordMarkSpecification><tmk:MarkSignificantVerbalElementText>GONE</tmk:MarkSignificantVerbalElementText></tmk:WordMarkSpecification></tmk:MarkReproduction></tmk:MarkRepresentation>"
           "<tmk:PublicationBag><tmk:Publication><tmk:PublicationSectionCategory>Registrations no longer in effect</tmk:PublicationSectionCategory><com:PublicationDate>2026-09-01</com:PublicationDate></tmk:Publication></tmk:PublicationBag></tmk:Trademark>"
           "</tmk:Transaction>")
    import tempfile, os
    fd, p = tempfile.mkstemp(suffix=".xml")
    os.write(fd, xml.encode()); os.close(fd)
    stats = {}
    recs = list(parse_file(p, stats))
    os.remove(p)
    assert len(recs) == 1, recs
    r = recs[0]
    assert r["serial"] == 99000001 and r["mark"] == "ACME ROCKET", r
    assert r["filing_date"] == "2026-03-27" and r["pub_date"] == "2026-09-01", r
    assert r["classes"] == [9, 42] and r["event"] == "published", r
    assert r["owner"] == "Acme Corp" and r["transaction_date"] == "2026-09-01", r
    assert stats == {"kept": 1, "design-only": 1, "section": 1}, stats
    print("tmog_parse selftest OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        selftest()
    elif len(sys.argv) > 2 and sys.argv[1] == "--probe":
        probe(sys.argv[2])
    else:
        for rec in parse_file(sys.argv[1]):
            print(json.dumps(rec, sort_keys=True))
