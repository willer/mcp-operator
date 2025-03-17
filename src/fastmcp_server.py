#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import uuid
from typing import Dict, Optional, Any

from fastmcp import FastMCP, Tool
from fastmcp.models import ToolCall, ToolCallResponse

from browser_operator import BrowserOperator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("mcp-operator.log")]
)
logger = logging.getLogger(__name__)

# Store browser instances
browser_operators: Dict[str, BrowserOperator] = {}

app = FastMCP(
    title="Browser Operator MCP",
    description="Control browser instances using Playwright",
)

@app.tool(
    name="browser_operator",
    description="Operates a browser to navigate websites, click elements, and fill forms.",
    parameters={
        "browser_id": {
            "type": "string",
            "description": "Optional browser instance ID to use an existing browser. If not provided, a new browser will be created."
        },
        "instruction": {
            "type": "string",
            "description": "The instruction to perform in the browser, such as 'navigate to google.com', 'click the search button', etc."
        }
    },
    required=["instruction"]
)
async def browser_operator(call: ToolCall) -> ToolCallResponse:
    """Operate a browser instance."""
    logger.info(f"Browser operator call: {call.parameters}")
    
    params = call.parameters
    browser_id = params.get("browser_id")
    instruction = params.get("instruction")
    
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
    
    return ToolCallResponse(
        content={
            "browser_id": browser_id,
            "output": result
        }
    )

@app.tool(
    name="browser_reset",
    description="Reset (close) a browser instance.",
    parameters={
        "browser_id": {
            "type": "string",
            "description": "The browser instance ID to reset."
        }
    },
    required=["browser_id"]
)
async def browser_reset(call: ToolCall) -> ToolCallResponse:
    """Reset a browser instance."""
    logger.info(f"Browser reset call: {call.parameters}")
    
    params = call.parameters
    browser_id = params.get("browser_id")
    
    if browser_id in browser_operators:
        operator = browser_operators[browser_id]
        await operator.close()
        del browser_operators[browser_id]
        return ToolCallResponse(
            content={
                "status": "reset",
                "browser_id": browser_id
            }
        )
    else:
        return ToolCallResponse(
            error=f"Browser ID not found: {browser_id}"
        )

@app.on_shutdown
async def shutdown_event():
    """Close all browser instances on shutdown."""
    for operator in browser_operators.values():
        await operator.close()

def main():
    """Run the FastMCP server."""
    # Get port from environment or use default (9978)
    port = int(os.environ.get("BROWSER_OPERATOR_PORT", "9978"))
    
    # Start the server
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()