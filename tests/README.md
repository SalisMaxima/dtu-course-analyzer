# DTU Course Analyzer - Test Suite

This directory contains validation and integration tests for the DTU Course Analyzer project.

## Test Files

### `validate_refactor.py`
Structural validation of the Phase 1 refactoring (14 tests):
- Directory structure validation
- Configuration module testing
- Utilities (logger, prepender) testing
- Parser modules (base, grade, review) testing
- Scraper modules (async, threaded) testing
- Analysis and validation modules testing
- Full import chain integration test

**Run with:**
```bash
python3 tests/validate_refactor.py
```

### `validate_pipeline.py`
End-to-end pipeline validation (5 tests):
- Configuration paths verification
- Parser pipeline with sample data
- Validation pipeline with course data
- Analysis pipeline with percentile calculation
- Backward compatibility verification

**Run with:**
```bash
python3 tests/validate_pipeline.py
```

## Running All Tests

Run both validation scripts:
```bash
python3 tests/validate_refactor.py && python3 tests/validate_pipeline.py
```

## Test Coverage

These tests validate:
- ✅ All 7 module directories exist with proper `__init__.py` files
- ✅ Configuration system loads and provides correct values
- ✅ Utility modules (logger, prepender) work correctly
- ✅ Parser modules process data correctly
- ✅ Scraper modules can be imported and initialized
- ✅ Analysis and validation modules process sample data
- ✅ Backward compatibility wrappers function correctly
- ✅ Full import chain works without conflicts

## Test Results

See `VALIDATION_REPORT.md` in the project root for detailed test results.
