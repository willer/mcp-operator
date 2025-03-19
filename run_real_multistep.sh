#!/bin/bash
# Script to run a real multi-step browser test that exercises the operate-browser functionality

# Set up colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Navigate to project root
cd "$(dirname "$0")"
echo -e "${YELLOW}===== MCP Operator Real Multi-Step Test =====${NC}"
echo -e "Running from: $(pwd)"

# Default options
HEADLESS=""
TASK="shopping"

# Process command line options
while [[ $# -gt 0 ]]; do
  case $1 in
    --headless)
      HEADLESS="--headless"
      shift
      ;;
    --task=*)
      TASK="${1#*=}"
      shift
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      echo -e "Usage: $0 [--headless] [--task=shopping|search|navigation]"
      exit 1
      ;;
  esac
done

# Show mode info
if [[ -n "$HEADLESS" ]]; then
    echo -e "${BLUE}Running in headless mode${NC}"
else
    echo -e "${BLUE}Running in visible mode (browser will be shown)${NC}"
    echo -e "${BLUE}Use --headless flag to run in headless mode${NC}"
fi

# Show task info
echo -e "${BLUE}Task: ${TASK}${NC}"
echo -e "${BLUE}Available tasks: shopping, search, navigation${NC}"
echo -e "${BLUE}Use --task=<name> to select a different task${NC}"

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

# Check if OPENAI_API_KEY is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}WARNING: OPENAI_API_KEY environment variable is not set!${NC}"
    echo -e "${YELLOW}This test requires a valid OpenAI API key to call the Computer Use API.${NC}"
    echo -e "${YELLOW}Please set OPENAI_API_KEY before running this test.${NC}"
    echo -e "${YELLOW}Example: export OPENAI_API_KEY='your-api-key-here'${NC}"
fi

# Run the real multi-step test directly
$PYTHON_CMD <<EOF
import sys, os
# Add src directory to path for imports
sys.path.insert(0, '$(pwd)/src')
sys.path.insert(0, '$(pwd)')

import asyncio
sys.argv = ['$0']
if '$HEADLESS':
    sys.argv.append('--headless')
sys.argv.append('--task=$TASK')

from tests.test_real_multistep import run_test
asyncio.run(run_test())
EOF

exit $?