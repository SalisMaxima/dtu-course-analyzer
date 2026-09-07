from pathlib import Path

from dtu_analyzer.analysis.analyzer import process_courses
from dtu_analyzer.parsers.grade_parser import parse_grades


def test_live_pass_fail_fixture_survives_analysis_without_numeric_average():
    html = (Path(__file__).parent / 'fixtures/01020-summer-2026.html').read_text()
    url = 'https://karakterer.dtu.dk/Histogram/1/01020/Summer-2026'
    sheet = parse_grades(html, url)
    assert sheet['participants'] == 92
    assert sheet['pass_percentage'] == 85
    assert sheet['Bestået'] == '79'
    assert sheet['Ikkebestået'] == '7'
    assert sheet['Ejmødt'] == '6'
    sheet.update(url=url, avg=0)  # Ignore a legacy bogus numeric average too.
    result = process_courses({'01020': {'grades': [sheet]}})['01020']
    assert result['grading_scale'] == 'pass_fail'
    assert result['grades'] == {'passed': '79', 'not_passed': '7', 'absent': '6'}
    assert 'avg' not in result and 'avgp' not in result
    assert result['grade_period'] == 'Summer-2026'
    assert result['grade_source'] == url


def test_numeric_course_still_has_grades_and_average():
    result = process_courses({'01001': {'grades': [{
        'participants': 10, 'pass_percentage': 90, 'avg': 6.3,
        '00': '1', '7': '9', 'Ejmødt': '0',
    }]}})['01001']
    assert result['grading_scale'] == 'seven_point'
    assert result['avg'] == 6.3
    assert result['grades']['7'] == '9'
    assert 'avgp' in result


def test_mixed_results_keep_both_kinds_of_awards():
    result = process_courses({'01001': {'grades': [{
        'participants': 10, 'pass_percentage': 90, 'avg': 7,
        '00': '1', '7': '1', 'Bestået': '8', 'Ikkebestået': '0',
    }]}})['01001']
    assert result['grading_scale'] == 'mixed'
    assert result['grades']['passed'] == '8'
    assert result['grades']['7'] == '1'
    assert 'avg' not in result and 'avgp' not in result


def test_approval_results_are_retained_separately():
    sheet = {'participants': 804, 'pass_percentage': 71, 'Bestået': '575',
             'Ikkebestået': '127', 'Godkendt': '0', 'IkkeGodkendt': '45', 'Ejmødt': '57'}
    result = process_courses({'01911': {'grades': [sheet]}})['01911']
    assert result['grades']['not_approved'] == '45'
    assert sum(int(v) for v in result['grades'].values()) == 804
    assert result['grading_scale'] == 'pass_fail'


def test_approval_only_results_have_no_numeric_average():
    sheet = {'participants': 10, 'pass_percentage': 90, 'Godkendt': '9', 'IkkeGodkendt': '1', 'avg': 0}
    result = process_courses({'12345': {'grades': [sheet]}})['12345']
    assert result['grading_scale'] == 'pass_fail'
    assert 'avg' not in result


def test_zero_categorical_placeholders_do_not_hide_numeric_average():
    sheet = {"participants": 10, "pass_percentage": 100, "7": "10",
             "Bestået": "0", "Ikkebestået": "0", "Godkendt": "0", "avg": 7}
    result = process_courses({"01001": {"grades": [sheet]}})["01001"]
    assert result["grading_scale"] == "seven_point"
    assert result["avg"] == 7
    assert "avgp" in result
    assert result["grades"]["passed"] == "0"


def test_zero_categorical_only_distribution_keeps_its_scale():
    from dtu_analyzer.analysis.analyzer import extract_grade_results
    for key in ("Bestået", "Godkendt"):
        counts, scale = extract_grade_results({key: "0", "Ejmødt": "1"})
        assert scale == "pass_fail"
        assert sum(int(v) for v in counts.values()) == 1


def test_positive_approval_and_numeric_results_are_mixed():
    from dtu_analyzer.analysis.analyzer import extract_grade_results
    counts, scale = extract_grade_results({"Godkendt": "1", "7": "1"})
    assert scale == "mixed"
    assert counts == {"approved": "1", "7": "1"}
