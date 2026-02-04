#!/bin/bash
#
# Setup script for DTU Course Analyzer
#
# This script sets up the development environment for the DTU Course Analyzer project.
# It installs Python dependencies and Playwright browsers.
#

set -e  # Exit on error

echo "================================"
echo "DTU Course Analyzer - Setup"
echo "================================"
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
minimum_version="3.10"
recommended_version="3.12"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo "ERROR: Python $minimum_version or higher is required"
    echo "Current version: $python_version"
    exit 1
fi

echo "✓ Python version: $python_version"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 12) else 1)"; then
    echo "⚠ Note: Python $recommended_version+ is recommended (you have $python_version)"
    echo "  Current version will work, but consider upgrading for best results"
fi
echo ""

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Install Playwright browsers
echo "Installing Playwright browsers..."
playwright install chromium
echo "✓ Playwright browsers installed"
echo ""

# Create necessary directories
echo "Creating directories..."
mkdir -p logs data
echo "✓ Directories created"
echo ""

# Check for environment variables (optional)
echo "Checking for DTU credentials..."
if [ -z "$DTU_USERNAME" ] || [ -z "$DTU_PASSWORD" ]; then
    echo "⚠ DTU_USERNAME and DTU_PASSWORD environment variables not set"
    echo "  You'll need to set these before running auth.py:"
    echo "  export DTU_USERNAME='your-username'"
    echo "  export DTU_PASSWORD='your-password'"
else
    echo "✓ DTU credentials found in environment"
fi
echo ""

echo "================================"
echo "✓ Setup complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "  1. Set DTU credentials (if not already set):"
echo "     export DTU_USERNAME='your-username'"
echo "     export DTU_PASSWORD='your-password'"
echo ""
echo "  2. Run authentication:"
echo "     python3 auth.py"
echo ""
echo "  3. Get course numbers:"
echo "     python3 getCourseNumbers.py"
echo ""
echo "  4. Run scraper:"
echo "     python3 scraper_async.py"
echo ""
echo "  5. Validate and analyze data:"
echo "     python3 validator.py coursedic.json"
echo "     python3 analyzer.py extension"
echo ""
