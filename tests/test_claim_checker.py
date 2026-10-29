"""Checks for skills/claim-checker scripts. Run: python -m pytest tests"""

import json
import subprocess
import sys
import gzip
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parents[1] / "skills" / "claim-checker" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from extract_claims import clean_url, sentences  # noqa: E402
from quote_check import html_to_text, quote_on_page  # noqa: E402

DRAFT = """# Title

Sales grew [12% in 2025](https://example.com/a?utm_source=x&id=7). The company is based in Pune.
It plans to hire 300 people. See https://example.com/b for details.

## Sources

- https://example.com/a
"""


MATCH = {"period": "n/a", "measure": "yes", "subject": "yes"}


def with_match(results):
    """Verified results need the checker's match check; tests about other rules add a passing one."""
    return [dict(r, match=r.get("match", MATCH)) if r.get("status") == "verified" else r for r in results]


def run(script, *args, cwd):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=cwd, capture_output=True, text=True)


def test_clean_url_drops_tracking_only():
    assert clean_url("https://example.com/a?utm_source=x&id=7.") == "https://example.com/a?id=7"


def test_links_with_dots_stay_in_one_sentence():
    s = sentences("See [v3.12 notes](https://docs.python.org/3/whatsnew/3.12.html). Next sentence.")
    assert len(s) == 2 and "3.12.html" in s[0]


def test_extract(tmp_path):
    (tmp_path / "d.md").write_text(DRAFT)
    r = run("extract_claims.py", "d.md", "--out", "c.json", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    c = json.loads((tmp_path / "c.json").read_text())
    assert [x["urls"] for x in c["claims"]] == [["https://example.com/a?id=7"], ["https://example.com/b"]]
    assert [u["sentence"] for u in c["uncited"]] == ["It plans to hire 300 people."]
    assert c["sources_section_urls"] == ["https://example.com/a"]


def test_report_refuses_missing_quote_and_unchecked_claim(tmp_path):
    (tmp_path / "d.md").write_text(DRAFT)
    run("extract_claims.py", "d.md", "--out", "c.json", cwd=tmp_path)
    (tmp_path / "k.json").write_text(json.dumps([{"id": 1, "status": "verified", "quote": ""}]))
    r = run("make_report.py", "c.json", "k.json", "--offline", cwd=tmp_path)
    assert r.returncode == 2
    out = json.loads(r.stdout)
    assert any("needs the supporting quote" in p for p in out["problems"])
    assert any("claim 2: no result" in p for p in out["problems"])


def test_report_tally(tmp_path):
    (tmp_path / "d.md").write_text(DRAFT)
    run("extract_claims.py", "d.md", "--out", "c.json", cwd=tmp_path)
    (tmp_path / "k.json").write_text(json.dumps([
        {"id": 1, "status": "partial", "quote": "Sales grew 10%", "note": "Source says 10%, not 12%."},
        {"id": 2, "status": "unverified", "note": "Page returned 404."},
    ]))
    r = run("make_report.py", "c.json", "k.json", "--out", "r.md", "--offline", cwd=tmp_path)
    assert r.returncode == 0, r.stdout
    report = (tmp_path / "r.md").read_text()
    assert "2 claims checked: 1 partial, 1 unverified." in report
    assert report.index("Unverified") < report.index("Partial")  # problems first, worst first


# ---- quote check: the quote must really be on the source page ----

PAGE = """<html><head><title>Release</title><script>var x = "Python is 25% faster";</script></head><body>
<h1>Python 3.12.0</h1>
<p>Python 3.12 is the newest major release, delivering an <b>estimated 5%</b> overall
performance improvement.</p>
<p>It’s a “big” release – with many changes.</p>
""" + "<p>More release notes and filler text for the page body.</p>" * 10 + "</body></html>"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        enc = None
        if self.path == "/release":
            body, ctype, code = PAGE.encode(), "text/html; charset=utf-8", 200
        elif self.path == "/gzipped":       # like python.org: compressed even though not asked
            body, ctype, code, enc = gzip.compress(PAGE.encode()), "text/html; charset=utf-8", 200, "gzip"
        elif self.path == "/binary":
            body, ctype, code = bytes(range(256)) * 20, "text/html", 200
        elif self.path == "/empty":
            body, ctype, code = b"<html><body><div id=app></div></body></html>", "text/html", 200
        else:
            body, ctype, code = b"not found", "text/plain", 404
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if enc:
            self.send_header("Content-Encoding", enc)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_quote_matching_rules():
    text = html_to_text(PAGE)
    assert "25% faster" not in text                                    # script text ignored
    assert quote_on_page("delivering an estimated 5% overall performance improvement", text)
    assert quote_on_page("It's a \"big\" release - with many changes.", text)   # straight vs curly marks
    assert quote_on_page("Python 3.12 is the newest … performance improvement", text)
    assert quote_on_page("performance improvement … Python 3.12 is the newest", text)  # parts in any order
    assert not quote_on_page("performance improvement … Python 3.13 is the newest", text)  # but every part must be there
    assert not quote_on_page("delivering an estimated 25% overall performance improvement", text)
    assert quote_on_page("Python 3.12 is the newest major release", text)
    assert not quote_on_page("Python 31.2 is the newest major release", text)   # digits keep their point


def _report(tmp_path, site, results, *extra):
    (tmp_path / "d.md").write_text(f"Python 3.12 is [5% faster]({site}/release). It is a [big release]({site}/release).")
    run("extract_claims.py", "d.md", "--out", "c.json", cwd=tmp_path)
    (tmp_path / "k.json").write_text(json.dumps(with_match(results)))
    return run("make_report.py", "c.json", "k.json", "--out", "r.md", *extra, cwd=tmp_path)


def test_fabricated_quote_is_refused(tmp_path, site):
    r = _report(tmp_path, site, [
        {"id": 1, "status": "verified", "url": f"{site}/release",
         "quote": "Python 3.12 delivers a 5% overall speed-up across all benchmarks."},  # plausible, not on page
        {"id": 2, "status": "verified", "url": f"{site}/release", "quote": "It's a big release with many changes."},
    ])
    assert r.returncode == 2, r.stdout
    problems = json.loads(r.stdout)["problems"]
    assert len(problems) == 1 and problems[0].startswith("claim 1: the quote was not found")


def test_real_quotes_pass_and_are_marked(tmp_path, site):
    r = _report(tmp_path, site, [
        {"id": 1, "status": "verified", "url": f"{site}/release",
         "quote": "delivering an estimated 5% overall performance improvement"},
        {"id": 2, "status": "verified", "url": f"{site}/release", "quote": "It's a \u201cbig\u201d release - with many changes."},
    ])
    assert r.returncode == 0, r.stdout
    assert json.loads(r.stdout)["quotes_found_on_page"] == 2
    report = (tmp_path / "r.md").read_text()
    assert "Quotes found on the downloaded source pages: 2 of 2." in report
    assert report.count("**Quote check:** found on the page.") == 2


def test_unreachable_page_is_flagged_not_passed(tmp_path, site):
    r = _report(tmp_path, site, [
        {"id": 1, "status": "verified", "url": f"{site}/missing", "quote": "delivering an estimated 5% overall"},
        {"id": 2, "status": "partial", "url": f"{site}/empty", "quote": "It's a big release with many changes.",
         "note": "Says big, not huge."},
    ])
    assert r.returncode == 0, r.stdout
    report = (tmp_path / "r.md").read_text()
    assert "Quotes found on the downloaded source pages: 0 of 2. 2 couldn't be machine-checked" in report
    assert "not machine-checked: the page wasn't found (error 404)" in report
    assert "not machine-checked: the downloaded page has almost no text" in report


def test_too_short_quote_is_refused(tmp_path, site):
    r = _report(tmp_path, site, [
        {"id": 1, "status": "verified", "url": f"{site}/release", "quote": "5%"},
        {"id": 2, "status": "unverified", "note": "Not checked."},
    ])
    assert r.returncode == 2
    assert "too short" in json.loads(r.stdout)["problems"][0]


def test_compressed_page_is_unpacked_and_garbage_is_not_checked(tmp_path, site):
    r = _report(tmp_path, site, [
        {"id": 1, "status": "verified", "url": f"{site}/gzipped",
         "quote": "delivering an estimated 5% overall performance improvement"},
        {"id": 2, "status": "verified", "url": f"{site}/binary", "quote": "It's a big release with many changes."},
    ])
    assert r.returncode == 0, r.stdout
    report = (tmp_path / "r.md").read_text()
    assert "Quotes found on the downloaded source pages: 1 of 2." in report
    assert "not machine-checked: the downloaded page couldn't be read as text" in report


def test_no_network_gives_one_clear_note(tmp_path):
    (tmp_path / "d.md").write_text("Sales grew [12% in 2025](https://blocked-site.invalid/a). "
                                   "The firm has [300 stores](https://blocked-site.invalid/b).")
    run("extract_claims.py", "d.md", "--out", "c.json", cwd=tmp_path)
    (tmp_path / "k.json").write_text(json.dumps(with_match([
        {"id": 1, "status": "verified", "url": "https://blocked-site.invalid/a", "quote": "Sales grew 12% in 2025."},
        {"id": 2, "status": "verified", "url": "https://blocked-site.invalid/b", "quote": "It now has 300 stores."},
    ])))
    r = run("make_report.py", "c.json", "k.json", "--out", "r.md", cwd=tmp_path)
    assert r.returncode == 0, r.stdout
    assert json.loads(r.stdout)["quote_check_off_in_sandbox"] is True
    report = (tmp_path / "r.md").read_text()
    assert "Quote check: off in this environment." in report and "not machine-checked:" not in report


# ---- numbers check: a verified claim's figures must be in its quote ----

from numbers_check import missing_figures  # noqa: E402


def test_numbers_rules():
    assert missing_figures("runs about 25% faster", "an estimated 5% overall improvement") == ["25%"]
    assert missing_figures("deprecated since Python 3.8", "In Python 3.10 and 3.11, deprecated") == ["3.8"]
    assert missing_figures("sold 1,29,940 units in Q1 FY27", "sold 129,940 units") == []      # Indian commas, labels ignored
    assert missing_figures("about 2.2 times", "a ratio of 2.17") == []                          # rounded to the claim's precision
    assert missing_figures("10% growth", "14% growth") == ["10%"]                                # small round numbers must be exact
    assert missing_figures("[Rs 15,664 crore](https://x.com/2026/07/a-123)", "Rs 15,664 crore") == []  # URL digits ignored
    assert missing_figures("3 companies lead", "nothing") == []                                  # small counts ignored


def _verified(tmp_path, claim_text, quote, **extra):
    (tmp_path / "d.md").write_text(f"[{claim_text}](https://example.com/a).")
    run("extract_claims.py", "d.md", "--out", "c.json", cwd=tmp_path)
    (tmp_path / "k.json").write_text(json.dumps(with_match([dict({"id": 1, "status": "verified", "quote": quote}, **extra)])))
    return run("make_report.py", "c.json", "k.json", "--out", "r.md", "--offline", cwd=tmp_path)


def test_real_quote_that_does_not_support_the_number_is_refused(tmp_path):
    r = _verified(tmp_path, "Python 3.12 runs about 25% faster than Python 3.11",
                  "Python 3.12 … 3.11 … delivering an estimated 5% overall performance improvement")
    assert r.returncode == 2
    assert "aren't in its quote: 25%" in json.loads(r.stdout)["problems"][0]


def test_explained_and_calculated_figures_are_shown_not_hidden(tmp_path):
    r = _verified(tmp_path, "Python 3.12 was released on 2 October 2023", "Release date: Oct. 2, 2023",
                  numbers_note="The source is the Python 3.12.0 release page itself.")
    assert r.returncode == 0, r.stdout
    assert "not in the quote: 3.12. Checker's explanation:" in (tmp_path / "r.md").read_text()
    r = _verified(tmp_path / "..", "Ather's revenue was about 2.7 times Ola's (calculated)", "revenue of ₹1,216.92 crore")
    assert r.returncode == 0, r.stdout
    assert "writer's own calculation" in (tmp_path / ".." / "r.md").read_text()


def test_k_suffix_counts_as_thousands():
    assert missing_figures("about 525,000 units", "approximately 525k units") == []


def _pdf(text):
    canvas = pytest.importorskip("reportlab.pdfgen.canvas")
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 800
    for line in text:
        c.drawString(40, y, line)
        y -= 16
    c.save()
    return buf.getvalue()


def test_pdf_sources_are_read(tmp_path):
    pytest.importorskip("pypdf")
    from quote_check import PDF_PREFIX, quote_on_page
    import quote_check
    pdf = _pdf(["Consolidated net loss for the quarter narrowed to Rs 51 crore from Rs 178 crore a year ago."]
               + ["Filler line of the results release for page length."] * 12)
    text, why = quote_check.pdf_text(pdf)
    assert text and text.startswith(PDF_PREFIX), why
    assert quote_on_page("net loss for the quarter narrowed to Rs 51 crore from Rs 178 crore", text)


# ---- v1.3: right number, wrong period / measure / subject ----
# Cases suggested by readers: a real quote with the right number for the wrong
# year, quarter, metric or population.

from numbers_check import missing_periods  # noqa: E402


def test_period_labels_must_match():
    assert missing_periods("Revenue grew 25% in FY27", "Revenue grew 25% in FY26") == ["FY27"]
    assert missing_periods("Revenue grew 25% in FY27", "revenue for fiscal 2027 grew 25%") == []
    assert missing_periods("Q2 FY27 sales rose 25%", "sales in the second quarter of FY2026-27 rose 25%") == []
    assert missing_periods("Q2 sales rose 25%", "Q1 sales rose 25%") == ["Q2"]
    assert missing_periods("H1 profit doubled", "first-half profit doubled") == []
    assert missing_periods("H1 profit doubled", "profit in the first half doubled") == []
    assert missing_periods("FY27 revenue", "revenue for 2026-27") == []          # Indian fiscal-year range


def test_wrong_year_or_period_with_the_right_number_is_refused(tmp_path):
    r = _verified(tmp_path, "Revenue grew 25% in 2025", "Revenue grew 25% in 2024")
    assert r.returncode == 2 and "aren't in its quote: 2025" in json.loads(r.stdout)["problems"][0]
    r = _verified(tmp_path, "Revenue grew 25% in FY27", "Revenue grew 25% in FY26")
    assert r.returncode == 2 and "aren't in its quote: FY27" in json.loads(r.stdout)["problems"][0]


def _matched(tmp_path, match):
    (tmp_path / "d.md").write_text("[25% of adults use the app](https://example.com/a).")
    run("extract_claims.py", "d.md", "--out", "c.json", cwd=tmp_path)
    res = {"id": 1, "status": "verified", "quote": "25% of teenagers use the app"}
    if match is not None:
        res["match"] = match
    (tmp_path / "k.json").write_text(json.dumps([res]))
    return run("make_report.py", "c.json", "k.json", "--out", "r.md", "--offline", cwd=tmp_path)


def test_match_check_is_required_for_verified(tmp_path):
    r = _matched(tmp_path, None)
    assert r.returncode == 2 and "needs the match check" in json.loads(r.stdout)["problems"][0]
    r = _matched(tmp_path, {"period": "n/a", "measure": "yes"})
    assert r.returncode == 2 and "yes, no or n/a for: subject" in json.loads(r.stdout)["problems"][0]


def test_wrong_population_or_metric_cannot_be_verified(tmp_path):
    r = _matched(tmp_path, {"period": "n/a", "measure": "yes", "subject": "no"})   # adults vs teenagers
    assert r.returncode == 2 and "different subject" in json.loads(r.stdout)["problems"][0]
    r = _matched(tmp_path, {"period": "yes", "measure": "no", "subject": "yes"})   # profit vs revenue
    assert r.returncode == 2 and "different measure" in json.loads(r.stdout)["problems"][0]


def test_match_check_is_shown_in_the_report(tmp_path):
    r = _matched(tmp_path, {"period": "N/A", "measure": "yes", "subject": "yes"})
    assert r.returncode == 0, r.stdout
    report = (tmp_path / "r.md").read_text()
    assert "Same period, measure and subject confirmed by the checker for 1 of 1 verified claim" in report
    assert "**Match check (checker's judgement):** same period: n/a, same measure: yes, same subject: yes." in report
