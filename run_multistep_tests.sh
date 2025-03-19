#!/bin/bash
# Script to run specifically the multi-step browser operation tests

# Set up colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Change to the project root directory
cd "$(dirname "$0")"
echo -e "${YELLOW}===== MCP Operator Multi-Step Tests =====${NC}"
echo -e "Running from: $(pwd)"

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

# Run the multi-step tests directly
$PYTHON_CMD <<EOF
import sys, os
# Add src directory to path for imports
sys.path.insert(0, '$(pwd)/src')
sys.path.insert(0, '$(pwd)')

import asyncio
from tests.test_multistep import run_tests
asyncio.run(run_tests())
EOF

exit $?