"""
Setup configuration for DTU Course Analyzer.

This file enables installation of the package via pip.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
requirements = []
if requirements_file.exists():
    requirements = [
        line.strip()
        for line in requirements_file.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

setup(
    name="dtu-course-analyzer",
    version="2.2.0",
    author="DTU Course Analyzer Contributors",
    description="Web scraper and browser extension for DTU course grade distributions and evaluations",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/SalisMaxima/dtu-course-analyzer",
    project_urls={
        "Bug Tracker": "https://github.com/SalisMaxima/dtu-course-analyzer/issues",
        "Source Code": "https://github.com/SalisMaxima/dtu-course-analyzer",
    },
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",  # Relaxed from 3.12 for broader compatibility
    install_requires=requirements,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Education",
        "Topic :: Education",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "dtu-auth=dtu_analyzer.auth.authenticator:main",
            "dtu-get-courses=dtu_analyzer.scripts.get_course_numbers:main",
            "dtu-scrape=dtu_analyzer.scrapers.async_scraper:main",
            "dtu-scrape-threaded=dtu_analyzer.scrapers.threaded_scraper:main",
            "dtu-validate=dtu_analyzer.validation.validator:main",
            "dtu-analyze=dtu_analyzer.analysis.analyzer:main",
        ],
    },
    keywords="dtu education scraper grades courses denmark university",
    include_package_data=True,
)
