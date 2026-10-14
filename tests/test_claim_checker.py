"""Checks for skills/claim-checker scripts. Run: python -m pytest tests"""

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[1] / "skills" / "claim-checker" / "scripts"
sys.path.insert(0, str(SCRIPTS))
from extract_claims import clean_url, sentences  # noqa: E402

DRAFT = """# Title

Sales grew [12% in 2025](https://example.com/a?utm_source=x&id=7). The company is based in Pune.
It plans to hire 300 people. See https://example.com/b for details.

## Sources

- https://example.com/a
"""


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
    r = run("make_report.py", "c.json", "k.json", cwd=tmp_path)
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
    r = run("make_report.py", "c.json", "k.json", "--out", "r.md", cwd=tmp_path)
    assert r.returncode == 0, r.stdout
    report = (tmp_path / "r.md").read_text()
    assert "2 claims checked: 1 partial, 1 unverified." in report
    assert report.index("Unverified") < report.index("Partial")  # problems first, worst first
