#!/usr/bin/env python3
"""End-to-end pipeline gate (keyless): synthetic TDXF XML -> tdxf_parse ->
fetch merge -> gen_index -> watch_run -> gen_seo. Everything downstream of the
USPTO download is exercised on data in the EXACT DTD shape the fetcher will
hand it, so the first key-in-hand run only has to validate the shape upstream
(tdxf_parse --probe) — not the whole chain.

Asserts:
  parse: pseudo-marks extracted, junk class codes skipped, broken case-file
         skipped without raising, dates normalized
  merge: new-serial detection feeds watch_run input
  index: gen_index.build accepts parser output
  watch: planted collision (NYKE ATHLETICS vs watched NIKE) alerts; noise
         doesn't; alert file honest (TSDR link + disclaimer)
  seo:   sitemap has 47 URLs (report + overview + 45 classes); planted mark
         on its class page; determinism (two builds byte-identical)

Fatal on any failure (exit 1) — wired into refresh.sh gates.
"""
import io
import os
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tdxf_parse            # noqa: E402
import fetch_trtdxfap as ft  # noqa: E402
import gen_index             # noqa: E402
import gen_seo               # noqa: E402
import watch_run             # noqa: E402


def case_file(serial, mark, filing, classes=(), pseudo=None, tx="20260830",
              broken=False):
    cls = "".join(
        "<classification><international-code-total-no>1"
        "</international-code-total-no><international-code>%s"
        "</international-code></classification>" % c for c in classes)
    stmts = ""
    if pseudo:
        stmts = ("<case-file-statements>"
                 "<case-file-statement><type-code>PM0001</type-code>"
                 "<text>%s</text></case-file-statement>"
                 "<case-file-statement><type-code>GS0251</type-code>"
                 "<text>widgets</text></case-file-statement>"
                 "</case-file-statements>" % pseudo)
    mark_el = "" if broken else "<mark-identification>%s</mark-identification>" % mark
    return ("<case-file><serial-number>%d</serial-number>"
            "<transaction-date>%s</transaction-date>"
            "<case-file-header><filing-date>%s</filing-date>"
            "<status-code>630</status-code>%s"
            "<mark-drawing-code>4000</mark-drawing-code></case-file-header>"
            "%s<classifications>%s</classifications>"
            "<case-file-owners><case-file-owner><party-name>Test LLC"
            "</party-name></case-file-owner></case-file-owners>"
            "</case-file>" % (serial, tx, filing, mark_el, stmts, cls))


def synth_zip(path):
    body = "".join([
        case_file(90000001, "NYKE ATHLETICS", "20260828", classes=["025"]),
        case_file(90000002, "BLUE RIVER CONSULTING", "20260829", classes=["035", "042"]),
        case_file(90000003, "TOTALLY UNRELATED COFFEE", "20260829",
                  classes=["030"], pseudo="NIKEY"),
        case_file(90000004, "JUNK CLASS MARK", "20260827", classes=["A", "200", "009"]),
        case_file(90000005, "", "20260827", broken=True),          # skipped
        case_file(90000006, "ANCIENT MARK", "20200101", classes=["009"]),  # aged out
    ])
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           "<trademark-applications-daily><version><version-no>2.3</version-no>"
           "</version><application-information><file-segments>"
           "<file-segment>TRMK</file-segment><action-keys>"
           "<action-key>Application</action-key>%s"
           "</action-keys></file-segments></application-information>"
           "</trademark-applications-daily>" % body)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("apc260830.xml", xml)


def main():
    with tempfile.TemporaryDirectory() as td:
        zp = os.path.join(td, "apc260830.zip")
        synth_zip(zp)

        # ---- parse
        recs = list(tdxf_parse.parse_file(zp))
        by = {r["serial"]: r for r in recs}
        assert len(recs) == 5, recs                      # broken one skipped
        assert by[90000001]["mark"] == "NYKE ATHLETICS"
        assert by[90000001]["filing_date"] == "2026-08-28"
        assert by[90000001]["classes"] == [25]
        assert by[90000003]["pseudo"] == ["NIKEY"]
        assert by[90000004]["classes"] == [9], by[90000004]   # A/200 skipped
        assert by[90000002]["classes"] == [35, 42]
        assert by[90000002]["owner"] == "Test LLC"

        # ---- merge (fetch logic): window drops ANCIENT, new serials flow out
        marks, new_rows, seen = ft.merge([], recs, [])
        assert 90000006 not in {r["serial"] for r in marks}   # >120d window
        assert {r["serial"] for r in new_rows} == {r["serial"] for r in recs}
        # second identical merge: nothing new
        _m2, new2, _s2 = ft.merge(marks, recs, seen)
        assert new2 == [], new2

        # ---- index accepts parser output
        idx_dir = os.path.join(td, "index")
        os.makedirs(idx_dir)
        gen_index.build(marks, idx_dir)
        assert os.path.exists(os.path.join(idx_dir, "manifest.json"))

        # ---- watch: planted collision fires, noise doesn't
        wl = {"s1": {"mark": "NIKE", "user": "alice", "start": "2026-09-01",
                     "expires": "2027-09-01"}}
        res = watch_run.run(wl, new_rows, "2026-08-30", out_dir=td)
        assert len(res) == 1 and res[0][3] == 2, res     # NYKE + pseudo NIKEY
        body = open(res[0][4]).read()
        assert "tsdr.uspto.gov" in body and "Not legal advice" in body
        assert "BLUE RIVER" not in body

        # ---- seo pages + determinism
        site1, site2 = os.path.join(td, "s1"), os.path.join(td, "s2")
        for sd in (site1, site2):
            os.makedirs(sd)
            n = gen_seo.build(marks, sd, "https://example.test/tm")
            assert n == 47, n
        c25 = open(os.path.join(site1, "filings", "class-25.html")).read()
        assert "NYKE ATHLETICS" in c25
        sm1 = open(os.path.join(site1, "sitemap.xml")).read()
        assert sm1.count("<url>") == 47
        for rel in ("sitemap.xml", os.path.join("filings", "index.html"),
                    os.path.join("filings", "class-25.html")):
            b1 = open(os.path.join(site1, rel), "rb").read()
            b2 = open(os.path.join(site2, rel), "rb").read()
            assert b1 == b2, "non-deterministic: %s" % rel

    print("selftest_e2e: PASS (parse, merge, index, watch, seo, determinism)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
