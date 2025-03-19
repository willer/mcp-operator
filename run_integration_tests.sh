#!/bin/bash
# Script to run browser integration tests with real Playwright browser

# Set up colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Navigate to project root
cd "$(dirname "$0")"
echo -e "${YELLOW}===== MCP Operator Browser Integration Tests =====${NC}"
echo -e "Running from: $(pwd)"

# Check for headless flag
HEADLESS=""
if [ "$1" == "--headless" ]; then
    HEADLESS="--headless"
    echo -e "${BLUE}Running in headless mode${NC}"
else
    echo -e "${BLUE}Running in visible mode (browser will be shown)${NC}"
    echo -e "${BLUE}Use --headless flag to run in headless mode${NC}"
fi

# Determine which Python command to use
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Error: Neither python nor python3 command found${NC}"
    exit 1
fi

echo -e "${GREEN}Using Python command: $PYTHON_CMD $(which $PYTHON_CMD)${NC}"

# Check if the mcp package is installed
if ! $PYTHON_CMD -c "import mcp" &> /dev/null; then
    echo -e "${RED}Error: The 'mcp' package is not installed.${NC}"
    echo -e "${YELLOW}Please install dependencies using:${NC}"
    echo -e "${GREEN}$PYTHON_CMD -m pip install -r requirements.txt${NC} or"
    echo -e "${GREEN}$PYTHON_CMD -m pip install -e .${NC}"
    exit 1
fi

# Check for playwright
if ! $PYTHON_CMD -c "import playwright" &> /dev/null; then
    echo -e "${RED}Error: Playwright not installed.${NC}"
    echo -e "${YELLOW}Installing playwright:${NC}"
    $PYTHON_CMD -m pip install playwright
    $PYTHON_CMD -m playwright install chromium
fi

# Run the integration tests directly
$PYTHON_CMD <<EOF
import sys, os
# Add src directory to path for imports
sys.path.insert(0, '$(pwd)/src')
sys.path.insert(0, '$(pwd)')

import asyncio
sys.argv = ['$0'] + ['$HEADLESS'] if '$HEADLESS' else ['$0']
from tests.integration_test_browser import run_tests
asyncio.run(run_tests())
EOF

exit $?