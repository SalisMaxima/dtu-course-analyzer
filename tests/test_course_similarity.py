"""Course description parsing and similarity neighbours."""

import asyncio
import json
from pathlib import Path
import subprocess

import numpy as np

from dtu_analyzer.analysis.course_similarity import (
    build_similarity, course_title, exclusion_map, nearest_neighbours, similarity_text,
)
from dtu_analyzer.parsers.course_page_parser import extract_course_codes, parse_course_page
from dtu_analyzer.scripts import build_course_similarity, scrape_course_details
from dtu_analyzer.scripts.candidate_provenance import runtime_hash

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_every_course_from_dtu_exclusion_notation():
    # Copied from kurser.dtu.dk/course/01001, soft hyphens included
    raw = "(01911.01922)(01901/­01910).01920)/­01003/­"
    assert extract_course_codes(raw) == ["01911", "01922", "01901", "01910", "01920", "01003"]
    assert extract_course_codes("42S01/KU002/2017") == ["42S01", "KU002"]


def test_parses_description_sections_and_exclusions():
    details = parse_course_page((FIXTURES / "course-page-01001.html").read_text())
    assert details["general_objectives"] == "To provide participants with a basic mathematical toolbox."
    assert "Solve linear systems of equations" in details["learning_objectives"]
    assert details["content"] == "Complex numbers, linear algebra and differential equations ."
    assert "May" not in details["content"]
    assert details["not_applicable_with"] == ["01911", "01922", "01901", "01910", "01920", "01003"]


def test_parses_danish_labels():
    html = """<table><tr><td>Pointspærring</td><td>02402</td></tr></table>
    <div class="bar">Læringsmål</div><ul><li>Regne</li></ul>
    <div class="bar">Indhold</div>Statistik
    <div class="bar">Bemærkninger</div>Ingen"""
    assert parse_course_page(html) == {
        "learning_objectives": "Regne", "content": "Statistik",
        "not_applicable_raw": "02402", "not_applicable_with": ["02402"],
    }


def test_page_without_description_yields_no_text():
    assert parse_course_page("<h2>01001 Title</h2>") == {}
    assert similarity_text("Title", {}) is None


def test_similarity_text_drops_boilerplate_and_prefixes_title():
    text = similarity_text("Mathematics 1a", {
        "learning_objectives": "A student who has met the objectives of the course will be able to: Compute",
        "content": "Matrices",
    })
    assert text == "Mathematics 1a. Compute Matrices"
    assert course_title({"name_en": "01001 Mathematics 1a", "name": "Matematik 1a"}) == "Mathematics 1a"
    assert course_title({"name": "Matematik 1a"}) == "Matematik 1a"


def test_exclusions_apply_in_both_directions():
    excluded = exclusion_map({"01001": {"not_applicable_with": ["01003", "01001"]}, "01003": {}})
    assert excluded == {"01001": {"01003"}, "01003": {"01001"}}


def test_equivalent_courses_are_never_neighbours():
    courses = ["01001", "01003", "01005", "02402"]
    vectors = np.array([[1, 0], [1, 0], [0.9, 0.1], [0, 1]], dtype=np.float32)
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    neighbours = nearest_neighbours(courses, vectors, {"01001": {"01003"}, "01003": {"01001"}}, top_k=2)
    assert [c for c, _ in neighbours["01001"]] == ["01005", "02402"]
    assert [c for c, _ in neighbours["01003"]] == ["01005", "02402"]
    # Without the exclusion the identical course would rank first
    assert nearest_neighbours(courses, vectors, {}, top_k=1)["01001"][0][0] == "01003"


def fake_encoder(_model_name):
    topics = ["linear algebra", "statistics", "machine learning"]

    def encode(texts):
        vectors = np.array([[t.lower().count(topic) + 0.01 for topic in topics] for t in texts], dtype=np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    return encode


DATA = {
    "01001": {"name_en": "01001 Mathematics 1a", "name": "Matematik 1a"},
    "01003": {"name_en": "01003 Mathematics 1a (English)"},
    "01005": {"name_en": "01005 Advanced Engineering Mathematics 1"},
    "02402": {"name_en": "02402 Introduction to Statistics"},
    "02450": {"name_en": "02450 Introduction to Machine Learning"},
    "99999": {"name_en": "99999 No description"},
}
DETAILS = {
    "01001": {"content": "Linear algebra", "not_applicable_with": ["01911", "01003"]},
    "01003": {"content": "Linear algebra"},
    "01005": {"content": "Linear algebra and statistics"},
    "02402": {"content": "Statistics"},
    "02450": {"content": "Machine learning and statistics"},
    "99999": {},
}


def test_build_similarity_skips_equivalent_and_undescribed_courses():
    neighbours, diagnostics = build_similarity(DATA, DETAILS, fake_encoder("x"), top_k=3)
    assert "99999" not in neighbours
    assert [c for c, _ in neighbours["01001"]][0] == "01005"
    assert "01003" not in [c for c, _ in neighbours["01001"]]
    assert "01001" not in [c for c, _ in neighbours["01003"]]
    assert diagnostics["without_description"] == ["99999"]
    assert diagnostics["excluded_pairs"] == 2


def test_build_script_writes_neighbours_and_report(tmp_path):
    (tmp_path / "data.json").write_text(json.dumps(DATA))
    (tmp_path / "details.json").write_text(json.dumps({"courses": DETAILS}))
    output, report = tmp_path / "similar.json", tmp_path / "report.md"
    code = build_course_similarity.main([
        "--data", str(tmp_path / "data.json"), "--details", str(tmp_path / "details.json"),
        "--output", str(output), "--report", str(report), "--top-k", "2", "--sample", "01001",
    ], encoder_factory=fake_encoder)
    assert code == 0
    written = json.loads(output.read_text())
    assert written["model"] == "google/embeddinggemma-2"
    assert len(written["courses"]["01001"]) == 2
    assert written["courses"]["01001"][0][0] == "01005"
    assert "01003" not in [c for c, _ in written["courses"]["01001"]]
    text = report.read_text()
    assert "## 01001 Mathematics 1a" in text
    assert "Excluded as equivalent: 01911, 01003" in text


def test_danish_page_fills_in_missing_english_description(monkeypatch):
    pages = {
        "en-GB": '<table><tr><td>Not applicable together with</td><td>01003</td></tr></table>',
        "da-DK": '<div class="bar">Indhold</div>Lineær algebra<div class="bar">Bemærkninger</div>',
    }
    requested = []

    async def fake_fetch(_session, url):
        requested.append(url)
        return pages[url.rsplit("=", 1)[1]]

    monkeypatch.setattr(scrape_course_details.async_scraper, "fetch_url", fake_fetch)
    course, details = asyncio.run(scrape_course_details.fetch_details(None, asyncio.Semaphore(1), "01001"))
    assert course == "01001"
    assert details == {"not_applicable_raw": "01003", "not_applicable_with": ["01003"],
                       "content": "Lineær algebra", "text_language": "da"}
    assert len(requested) == 2


def test_english_description_skips_danish_request(monkeypatch):
    requested = []

    async def fake_fetch(_session, url):
        requested.append(url)
        return (FIXTURES / "course-page-01001.html").read_text()

    monkeypatch.setattr(scrape_course_details.async_scraper, "fetch_url", fake_fetch)
    _, details = asyncio.run(scrape_course_details.fetch_details(None, asyncio.Semaphore(1), "01001"))
    assert requested == ["https://kurser.dtu.dk/course/01001?lang=en-GB"]
    assert "text_language" not in details


def test_similarity_data_does_not_change_candidate_runtime_hash(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "extension/db").mkdir(parents=True)
    (tmp_path / "extension/db/similar.json").write_text("{}")
    (tmp_path / "extension/contentscript.js").write_text("// code")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    before = runtime_hash(tmp_path)
    (tmp_path / "extension/db/similar.json").write_text('{"courses": {}}')
    assert runtime_hash(tmp_path) == before
    (tmp_path / "extension/contentscript.js").write_text("// changed")
    assert runtime_hash(tmp_path) != before
