#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Dict, Optional, Any, List

# Configure logging - use stderr for messages and file for debugging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("browser-operator.log"), 
        logging.StreamHandler(sys.stderr)
    ]
)
logger = logging.getLogger(__name__)

# Try importing mcp.server.fastmcp - this matches how the reminders MCP works
try:
    from mcp.server.fastmcp import FastMCP
    logger.info("Successfully imported FastMCP from mcp.server.fastmcp")
except ImportError:
    try:
        from fastmcp import FastMCP
        logger.info("Successfully imported FastMCP from fastmcp")
    except ImportError:
        logger.error("FastMCP not found, please install with: pip install fastmcp")
        sys.exit(1)

# Import our browser operator
try:
    from browser_operator import BrowserOperator
except ImportError:
    try:
        from src.browser_operator import BrowserOperator
    except ImportError:
        logger.error("Could not import BrowserOperator")
        sys.exit(1)

# Store browser instances
browser_operators = {}

# Create the MCP server
mcp = FastMCP("Browser Operator")

@mcp.tool()
def browser_operator(browser_id: Optional[str] = None, instruction: str = None) -> Dict[str, Any]:
    """
    Operates a browser to navigate websites, click elements, and fill forms.
    
    Args:
        browser_id: Optional browser instance ID to use an existing browser. If not provided, a new browser will be created.
        instruction: The instruction to perform in the browser, such as 'navigate to google.com', 'click the search button', etc.
    
    Returns:
        A dictionary containing the browser ID and the output from the operation.
    """
    logger.info(f"Browser operator called with ID: {browser_id}, instruction: {instruction}")
    
    # This is a blocking function, we need to run the async code in a new event loop
    return asyncio.run(_browser_operator(browser_id, instruction))
    
async def _browser_operator(browser_id: Optional[str], instruction: str) -> Dict[str, Any]:
    """Async implementation of browser_operator."""
    # Get or create a browser operator
    if browser_id and browser_id in browser_operators:
        operator = browser_operators[browser_id]
    else:
        # Create a new browser instance
        browser_id = str(uuid.uuid4())
        operator = BrowserOperator(browser_id)
        browser_operators[browser_id] = operator
        await operator.initialize()
    
    # Process the instruction
    result = await operator.process_message(instruction)
    
    return {
        "browser_id": browser_id,
        "output": result
    }

@mcp.tool()
def browser_reset(browser_id: str) -> Dict[str, Any]:
    """
    Reset (close) a browser instance.
    
    Args:
        browser_id: The browser instance ID to reset.
        
    Returns:
        A dictionary containing the status and browser ID.
    """
    logger.info(f"Browser reset called with ID: {browser_id}")
    
    # This is a blocking function, we need to run the async code in a new event loop
    return asyncio.run(_browser_reset(browser_id))

async def _browser_reset(browser_id: str) -> Dict[str, Any]:
    """Async implementation of browser_reset."""
    if browser_id in browser_operators:
        operator = browser_operators[browser_id]
        await operator.close()
        del browser_operators[browser_id]
        return {
            "status": "reset",
            "browser_id": browser_id
        }
    else:
        raise ValueError(f"Browser ID not found: {browser_id}")

def main():
    """Run the FastMCP server."""
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Print a message to stderr for debugging
    print("Starting Browser Operator MCP server", file=sys.stderr)
    
    try:
        # Run the MCP server
        mcp.run()
    except Exception as e:
        logger.exception(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()