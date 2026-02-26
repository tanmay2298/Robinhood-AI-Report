#!/bin/bash

# Weekly Portfolio Report - Automated Execution Script
# This script is designed to run via launchd scheduler

# Log execution start
echo "=================================================="
echo "Portfolio Report Execution Started"
echo "Date: $(date)"
echo "=================================================="
echo ""

# Source environment variables from ~/.zshrc
echo "Loading environment variables from ~/.zshrc..."
if [ -f "$HOME/.zshrc" ]; then
    source "$HOME/.zshrc"
    echo "✓ Environment variables loaded"
else
    echo "✗ Error: ~/.zshrc not found"
    exit 1
fi

# Change to project directory (resolve to the directory this script lives in)
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Changing to project directory: $PROJECT_DIR"
cd "$PROJECT_DIR" || {
    echo "✗ Error: Could not change to project directory"
    exit 1
}
echo "✓ Changed to project directory"
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✓ Virtual environment activated"
else
    echo "✗ Error: Virtual environment not found at venv/bin/activate"
    exit 1
fi
echo ""

# Verify required environment variables
echo "Verifying required environment variables..."
missing_vars=0
for var in ROBINHOOD_EMAIL ROBINHOOD_PASSWORD ANTHROPIC_API_KEY TAVILY_API_KEY; do
    if [ -z "${!var}" ]; then
        echo "✗ Missing: $var"
        missing_vars=1
    else
        echo "✓ Found: $var"
    fi
done

if [ $missing_vars -eq 1 ]; then
    echo ""
    echo "✗ Error: Missing required environment variables"
    exit 1
fi
echo ""

# Run report generation with --no-open flag
echo "Starting report generation..."
echo "=================================================="
python3 weekly_report_gen.py --no-open
exit_code=$?
echo "=================================================="
echo ""

# Check execution result
if [ $exit_code -eq 0 ]; then
    echo "✓ Report generation completed successfully"
else
    echo "✗ Report generation failed with exit code: $exit_code"
fi

echo ""
echo "=================================================="
echo "Portfolio Report Execution Finished"
echo "Date: $(date)"
echo "Exit Code: $exit_code"
echo "=================================================="

exit $exit_code
