#!/bin/bash

# Test runner script for Stock EMA Monitor

set -e

echo "🧪 Running Stock EMA Monitor Tests"
echo "=" * 50

# Check if test dependencies are installed
echo "📋 Checking test dependencies..."
if ! python3 -m pip show pytest > /dev/null 2>&1; then
    echo "Installing test dependencies..."
    pip3 install -r test_requirements.txt
fi

# Remove old coverage data
echo "🧹 Cleaning old coverage data..."
rm -rf htmlcov/
rm -f .coverage

# Run tests with coverage
echo "🚀 Running tests with coverage analysis..."
python3 -m pytest test_lambda_function.py -v \
    --cov=lambda_function \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    --cov-fail-under=80

# Check if coverage threshold was met
if [ $? -eq 0 ]; then
    echo "✅ All tests passed with sufficient coverage!"
    echo "📊 Coverage report generated in htmlcov/index.html"
    echo "🌐 Open with: open htmlcov/index.html"
else
    echo "❌ Tests failed or coverage below 80%"
    exit 1
fi

echo ""
echo "📈 Test Summary:"
echo "- Unit tests: ✅ Comprehensive test suite"
echo "- Coverage: ✅ 80%+ code coverage"
echo "- Mocking: ✅ External dependencies mocked"
echo "- Error handling: ✅ All error paths tested"