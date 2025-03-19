#!/bin/bash
# Script to run the MCP Operator tests with proper environment setup

# Set up colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Navigate to project root
cd "$(dirname "$0")"

echo -e "${YELLOW}===== MCP Operator Test Runner =====${NC}"
echo -e "Running tests from: $(pwd)"

# Check for Python environment - try to use the virtual environment if it exists
if [ -d "venv" ]; then
    echo -e "${GREEN}Using virtual environment in ./venv${NC}"
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo -e "${GREEN}Using virtual environment in ./.venv${NC}"
    source .venv/bin/activate
elif [ -n "$VIRTUAL_ENV" ]; then
    echo -e "${GREEN}Using active virtual environment: $VIRTUAL_ENV${NC}"
else
    echo -e "${YELLOW}No virtual environment detected, using system Python${NC}"
fi

# Add current directory to PYTHONPATH
export PYTHONPATH="$PYTHONPATH:$(pwd)"

# Determine which Python command to use
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Neither python nor python3 command found${NC}"
    exit 1
fi

echo -e "${GREEN}Using Python command: $PYTHON_CMD$(which $PYTHON_CMD)${NC}"

# Check if the mcp package is installed
if ! $PYTHON_CMD -c "import mcp" &> /dev/null; then
    echo -e "${RED}Error: The 'mcp' package is not installed.${NC}"
    echo -e "${YELLOW}Please install dependencies using:${NC}"
    echo -e "${GREEN}$PYTHON_CMD -m pip install -r requirements.txt${NC} or"
    echo -e "${GREEN}$PYTHON_CMD -m pip install -e .${NC}"
    exit 1
fi

echo -e "\n${YELLOW}===== Running core tests =====${NC}"
$PYTHON_CMD <<EOF
import sys, os
# Add src directory to path for imports
sys.path.insert(0, '$(pwd)/src')
sys.path.insert(0, '$(pwd)')

import asyncio
from tests.run_tests import run_tests
asyncio.run(run_tests())
EOF

CORE_STATUS=$?

echo -e "\n${YELLOW}===== Running multi-step specific tests =====${NC}"
$PYTHON_CMD <<EOF
import sys, os
# Add src directory to path for imports
sys.path.insert(0, '$(pwd)/src')
sys.path.insert(0, '$(pwd)')

import asyncio
from tests.test_multistep import run_tests
asyncio.run(run_tests())
EOF

MULTISTEP_STATUS=$?

if [ $CORE_STATUS -eq 0 ] && [ $MULTISTEP_STATUS -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed successfully!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Some tests failed${NC}"
    if [ $CORE_STATUS -ne 0 ]; then
        echo -e "${RED}Core tests failed with status $CORE_STATUS${NC}"
    fi
    if [ $MULTISTEP_STATUS -ne 0 ]; then
        echo -e "${RED}Multi-step tests failed with status $MULTISTEP_STATUS${NC}"
    fi
    exit 1
fi