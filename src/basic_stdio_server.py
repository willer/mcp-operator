#!/usr/bin/env python3

import asyncio
import sys
import json
import logging
import os
import uuid
from typing import Dict, Optional, Any

# Set up logging to a file only
log_file = "browser-operator.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file)]
)
logger = logging.getLogger(__name__)

# Try importing our browser operator
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

async def stdin_reader():
    """Read JSON-RPC requests from stdin."""
    while True:
        try:
            # Read a line from stdin
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            if not line:
                logger.info("End of input, exiting")
                break
                
            # Log the raw input
            logger.info(f"Received raw input: {line.strip()}")
            
            # Parse JSON
            request = json.loads(line)
            logger.info(f"Parsed request: {request}")
            
            # Process the request
            response = await handle_request(request)
            
            # Log the response
            logger.info(f"Sending response: {response}")
            
            # Send the response
            print(json.dumps(response), flush=True)
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            }), flush=True)
            
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": f"Internal error: {str(e)}"
                }
            }), flush=True)

async def handle_request(request):
    """Handle a JSON-RPC request."""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    logger.info(f"Processing method: {method} with params: {params}")
    
    if method == "initialize":
        # Simple initialization response without version
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "name": "browser-operator",
                "version": "0.1.0",
                "capabilities": {}
            }
        }
        
    elif method == "tools.list":
        # Return available tools
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": [
                {
                    "name": "browser_operator",
                    "description": "Operates a browser to navigate websites",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "browser_id": {
                                "type": "string",
                                "description": "Optional browser ID to use an existing browser"
                            },
                            "instruction": {
                                "type": "string",
                                "description": "The instruction to perform in the browser"
                            }
                        },
                        "required": ["instruction"]
                    }
                },
                {
                    "name": "browser_reset",
                    "description": "Reset a browser instance",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "browser_id": {
                                "type": "string",
                                "description": "The browser ID to reset"
                            }
                        },
                        "required": ["browser_id"]
                    }
                }
            ]
        }
        
    elif method == "browser_operator":
        # Get parameters
        browser_id = params.get("browser_id")
        instruction = params.get("instruction")
        
        if not instruction:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: instruction"
                }
            }
        
        # Get or create browser operator
        if browser_id and browser_id in browser_operators:
            operator = browser_operators[browser_id]
        else:
            # Create new browser instance
            browser_id = str(uuid.uuid4())
            operator = BrowserOperator(browser_id)
            browser_operators[browser_id] = operator
            await operator.initialize()
        
        # Process the instruction
        result = await operator.process_message(instruction)
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "browser_id": browser_id,
                "output": result
            }
        }
        
    elif method == "browser_reset":
        # Get parameters
        browser_id = params.get("browser_id")
        
        if not browser_id:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: browser_id"
                }
            }
        
        # Find and close the browser
        if browser_id in browser_operators:
            operator = browser_operators[browser_id]
            await operator.close()
            del browser_operators[browser_id]
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "status": "reset",
                    "browser_id": browser_id
                }
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32602,
                    "message": f"Browser ID not found: {browser_id}"
                }
            }
            
    else:
        # Method not found
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }

async def main():
    """Main entry point."""
    # Print a debug message to stderr
    print("Browser Operator MCP Server starting", file=sys.stderr)
    
    try:
        # Run the stdin reader
        await stdin_reader()
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())