#!/usr/bin/env python3
"""
Validation script for Phase 1 refactoring (Steps 1-6).

Tests that all migrated modules work correctly and backward compatibility is maintained.
"""

import sys
import json
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Test results tracking
tests_passed = 0
tests_failed = 0
errors = []

def test(description: str):
    """Decorator for test functions."""
    def decorator(func):
        def wrapper():
            global tests_passed, tests_failed, errors
            try:
                print(f"\n{'='*60}")
                print(f"Testing: {description}")
                print('='*60)
                func()
                print(f"✅ PASSED: {description}")
                tests_passed += 1
            except Exception as e:
                print(f"❌ FAILED: {description}")
                print(f"   Error: {e}")
                errors.append((description, str(e)))
                tests_failed += 1
        return wrapper
    return decorator


@test("Step 1: Directory structure exists")
def test_directory_structure():
    """Verify all directories were created."""
    required_dirs = [
        "src/dtu_analyzer",
        "src/dtu_analyzer/scrapers",
        "src/dtu_analyzer/parsers",
        "src/dtu_analyzer/utils",
        "src/dtu_analyzer/analysis",
        "src/dtu_analyzer/validation",
        "src/dtu_analyzer/auth",
    ]

    for dir_path in required_dirs:
        path = Path(dir_path)
        assert path.exists(), f"Directory {dir_path} does not exist"
        assert path.is_dir(), f"{dir_path} is not a directory"

        # Check for __init__.py
        init_file = path / "__init__.py"
        assert init_file.exists(), f"Missing __init__.py in {dir_path}"

    print(f"   All {len(required_dirs)} directories exist with __init__.py files")


@test("Step 2: Configuration module works")
def test_configuration():
    """Test that config module loads and provides correct values."""
    from src.dtu_analyzer.config import config

    # Test that config object exists
    assert config is not None, "Config object is None"

    # Test scraper config
    assert hasattr(config, 'scraper'), "Config missing scraper section"
    assert config.scraper.max_concurrent == 2, f"Expected max_concurrent=2, got {config.scraper.max_concurrent}"
    assert config.scraper.timeout == 30, f"Expected timeout=30, got {config.scraper.timeout}"
    assert config.scraper.base_url == "http://kurser.dtu.dk", f"Unexpected base_url: {config.scraper.base_url}"

    # Test paths config
    assert hasattr(config, 'paths'), "Config missing paths section"
    assert hasattr(config.paths, 'course_data_file'), "Paths missing course_data_file"
    assert hasattr(config.paths, 'course_numbers_file'), "Paths missing course_numbers_file"
    assert hasattr(config.paths, 'secret_file'), "Paths missing secret_file"

    print(f"   Config loaded: max_concurrent={config.scraper.max_concurrent}, timeout={config.scraper.timeout}")
    print(f"   Course data file: {config.paths.course_data_file}")


@test("Step 3: Utilities module (logger)")
def test_logger():
    """Test that logger utility works from new location."""
    from src.dtu_analyzer.utils.logger import setup_logger, get_scraper_logger

    # Test setup_logger
    test_logger = setup_logger('test_logger', 'test.log')
    assert test_logger is not None, "setup_logger returned None"
    assert test_logger.name == 'test_logger', f"Logger name is {test_logger.name}, expected 'test_logger'"

    # Test get_scraper_logger
    scraper_logger = get_scraper_logger()
    assert scraper_logger is not None, "get_scraper_logger returned None"

    # Test that logger can write
    test_logger.info("Test log message")

    print(f"   Logger created successfully: {test_logger.name}")


@test("Step 3: Utilities module (prepender)")
def test_prepender():
    """Test that PrependToFile utility works from new location."""
    from src.dtu_analyzer.utils.prepender import PrependToFile
    import tempfile
    import os

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        f.write("Line 2\nLine 3\n")
        temp_path = f.name

    try:
        # Test prepending
        with PrependToFile(temp_path) as p:
            p.write_line("Line 1")

        # Verify content
        with open(temp_path, 'r') as f:
            content = f.read()
            assert content.startswith("Line 1\n"), "Prepend failed"
            assert "Line 2" in content, "Original content missing"

        print(f"   PrependToFile works correctly")
    finally:
        os.unlink(temp_path)


@test("Step 4: Parser module (base utilities)")
def test_base_parser():
    """Test base parser utilities."""
    from src.dtu_analyzer.parsers.base import remove_whitespace, parse_year

    # Test remove_whitespace
    assert remove_whitespace("  hello   world  ") == "helloworld"
    assert remove_whitespace("test") == "test"

    # Test parse_year
    assert parse_year("24") == "2024", f"parse_year('24') returned {parse_year('24')}"
    assert parse_year("99") == "1999", f"parse_year('99') returned {parse_year('99')}"
    assert parse_year("2024") == "2024", f"parse_year('2024') returned {parse_year('2024')}"

    print(f"   Base parser utilities work correctly")


@test("Step 4: Parser module (grade parser)")
def test_grade_parser():
    """Test grade parser can be imported and has correct structure."""
    from src.dtu_analyzer.parsers.grade_parser import parse_grades

    # Verify function exists and is callable
    assert callable(parse_grades), "parse_grades is not callable"

    # Test with minimal HTML (won't parse successfully but shouldn't crash)
    result = parse_grades("<html><body></body></html>", "http://test.com")
    # Should return None for invalid HTML
    assert result is None or isinstance(result, dict), "parse_grades returned unexpected type"

    print(f"   Grade parser imported successfully")


@test("Step 4: Parser module (review parser)")
def test_review_parser():
    """Test review parser can be imported and has correct structure."""
    from src.dtu_analyzer.parsers.review_parser import parse_reviews

    # Verify function exists and is callable
    assert callable(parse_reviews), "parse_reviews is not callable"

    # Test with minimal HTML (won't parse successfully but shouldn't crash)
    result = parse_reviews("<html><body></body></html>", "http://test.com")
    # Should return None for invalid HTML
    assert result is None or isinstance(result, dict), "parse_reviews returned unexpected type"

    print(f"   Review parser imported successfully")


@test("Step 5: Scraper module (async scraper)")
def test_async_scraper():
    """Test async scraper can be imported."""
    from src.dtu_analyzer.scrapers.async_scraper import main, fetch_url, process_single_course

    # Verify main function exists
    assert callable(main), "async_scraper main is not callable"
    assert callable(fetch_url), "fetch_url is not callable"
    assert callable(process_single_course), "process_single_course is not callable"

    print(f"   Async scraper imported successfully")


@test("Step 5: Scraper module (threaded scraper)")
def test_threaded_scraper():
    """Test threaded scraper can be imported."""
    from src.dtu_analyzer.scrapers.threaded_scraper import main, Course, process_single_course

    # Verify main function exists
    assert callable(main), "threaded_scraper main is not callable"
    assert callable(process_single_course), "process_single_course is not callable"

    # Test Course class
    course = Course("01234")
    assert course.courseN == "01234", "Course initialization failed"

    print(f"   Threaded scraper imported successfully")


@test("Step 5: Backward compatibility (scrapers)")
def test_scraper_wrappers():
    """Test backward-compatible scraper wrappers."""
    # Test async scraper wrapper
    import scraper_async
    assert hasattr(scraper_async, 'main'), "scraper_async wrapper missing main"

    # Test threaded scraper wrapper
    import scraper
    assert hasattr(scraper, 'main'), "scraper wrapper missing main"

    print(f"   Scraper wrappers work correctly")


@test("Step 6: Analysis module")
def test_analyzer():
    """Test analyzer module can be imported."""
    from src.dtu_analyzer.analysis.analyzer import main, process_courses, calcScore

    # Verify functions exist
    assert callable(main), "analyzer main is not callable"
    assert callable(process_courses), "process_courses is not callable"
    assert callable(calcScore), "calcScore is not callable"

    # Test calcScore with simple data
    test_data = {
        "question": "Test question",
        "0": "10",
        "1": "20",
        "2": "15"
    }
    score = calcScore(test_data, bestOptionFirst=True)
    assert isinstance(score, float), "calcScore should return float"
    assert 1.0 <= score <= 5.0, f"Score {score} out of expected range"

    print(f"   Analyzer imported and tested successfully")


@test("Step 6: Validation module")
def test_validator():
    """Test validator module can be imported."""
    from src.dtu_analyzer.validation.validator import main, CourseDataValidator, validate_file

    # Verify functions exist
    assert callable(main), "validator main is not callable"
    assert callable(validate_file), "validate_file is not callable"

    # Test CourseDataValidator with minimal data
    test_data = {
        "01234": {
            "name": "Test Course",
            "grades": [{
                "timestamp": "E24",
                "participants": 100
            }]
        }
    }

    validator = CourseDataValidator(test_data)
    result = validator.validate()
    assert isinstance(result, bool), "validator.validate() should return bool"

    summary = validator.get_summary()
    assert "total_courses" in summary, "Summary missing total_courses"
    assert summary["total_courses"] == 1, f"Expected 1 course, got {summary['total_courses']}"

    print(f"   Validator imported and tested successfully")


@test("Step 6: Backward compatibility (analysis/validation)")
def test_analysis_validation_wrappers():
    """Test backward-compatible wrappers for analyzer and validator."""
    # Test analyzer wrapper
    import analyzer
    assert hasattr(analyzer, 'main'), "analyzer wrapper missing main"

    # Test validator wrapper
    import validator
    assert hasattr(validator, 'main'), "validator wrapper missing main"

    print(f"   Analysis/validation wrappers work correctly")


@test("Integration: Full import chain")
def test_full_import_chain():
    """Test that all modules can be imported together without conflicts."""
    # Import everything to check for conflicts
    from src.dtu_analyzer import __version__
    from src.dtu_analyzer.config import config
    from src.dtu_analyzer.utils.logger import get_scraper_logger
    from src.dtu_analyzer.utils.prepender import PrependToFile
    from src.dtu_analyzer.parsers.base import parse_year
    from src.dtu_analyzer.parsers.grade_parser import parse_grades
    from src.dtu_analyzer.parsers.review_parser import parse_reviews
    from src.dtu_analyzer.scrapers.async_scraper import main as async_main
    from src.dtu_analyzer.scrapers.threaded_scraper import main as threaded_main
    from src.dtu_analyzer.analysis.analyzer import main as analyze_main
    from src.dtu_analyzer.validation.validator import main as validate_main

    # Also import wrappers
    import scraper
    import scraper_async
    import analyzer
    import validator

    print(f"   All modules imported successfully")
    print(f"   Package version: {__version__}")


def main():
    """Run all validation tests."""
    print("\n" + "="*60)
    print("Phase 1 Refactoring Validation (Steps 1-6)")
    print("="*60)

    # Run all tests
    test_directory_structure()
    test_configuration()
    test_logger()
    test_prepender()
    test_base_parser()
    test_grade_parser()
    test_review_parser()
    test_async_scraper()
    test_threaded_scraper()
    test_scraper_wrappers()
    test_analyzer()
    test_validator()
    test_analysis_validation_wrappers()
    test_full_import_chain()

    # Print summary
    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    print(f"✅ Tests passed: {tests_passed}")
    print(f"❌ Tests failed: {tests_failed}")

    if errors:
        print("\nFailed tests:")
        for desc, error in errors:
            print(f"  - {desc}")
            print(f"    {error}")

    print("="*60)

    if tests_failed == 0:
        print("\n🎉 ALL TESTS PASSED! Phase 1 refactoring is validated.")
        return 0
    else:
        print(f"\n⚠️  {tests_failed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
