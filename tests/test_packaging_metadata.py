from pathlib import Path
import tomllib


def test_pyproject_playwright_dependency_matches_requirements() -> None:
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text())
    requirements = (root / "requirements.txt").read_text().splitlines()

    pyproject_playwright = next(
        dependency
        for dependency in pyproject["project"]["dependencies"]
        if dependency.startswith("playwright")
    )
    requirements_playwright = next(
        requirement.strip()
        for requirement in requirements
        if requirement.strip().startswith("playwright")
    )

    assert pyproject_playwright == requirements_playwright
