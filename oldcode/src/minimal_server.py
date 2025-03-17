#!/usr/bin/env python3

import asyncio
import json
import logging
import sys
import os
import uuid
from typing import Dict, Any

# Set up logging to a file only
log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp-operator.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file)]
)
logger = logging.getLogger(__name__)

# Try importing BrowserOperator
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

async def main():
    """Main entry point for the minimal MCP server."""
    logger.info("Starting minimal MCP server")
    
    # Print a marker to stderr (not stdout)
    print("Browser Operator MCP Server running on stdio", file=sys.stderr)
    
    while True:
        try:
            # Read a line from stdin
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                logger.info("End of input stream, exiting")
                break
            
            # Parse the JSON
            try:
                request = json.loads(line)
                logger.info(f"Received request: {request}")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                continue
            
            # Process the request
            response = await process_request(request)
            
            # Send the response
            if response:
                print(json.dumps(response), flush=True)
                
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            
async def process_request(request):
    """Process a single JSON-RPC request."""
    try:
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")
        
        if method == "initialize":
            # Initialization response following exact format from docs
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "logging": {},
                        "prompts": {
                            "listChanged": true
                        },
                        "resources": {
                            "subscribe": true,
                            "listChanged": true
                        },
                        "tools": {
                            "listChanged": true
                        }
                    },
                    "serverInfo": {
                        "name": "BrowserOperator",
                        "version": "0.1.0"
                    }
                }
            }
            
        elif method == "browser_operator":
            # Handle browser operation
            browser_id = params.get("browser_id")
            instruction = params.get("instruction")
            
            if not instruction:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": "Missing required parameter: instruction"
                    }
                }
            
            # Get or create browser operator
            if browser_id and browser_id in browser_operators:
                operator = browser_operators[browser_id]
            else:
                browser_id = str(uuid.uuid4())
                operator = BrowserOperator(browser_id)
                browser_operators[browser_id] = operator
                await operator.initialize()
            
            # Process the instruction
            result = await operator.process_message(instruction)
            
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "browser_id": browser_id,
                    "output": result
                }
            }
            
        elif method == "browser_reset":
            # Handle browser reset
            browser_id = params.get("browser_id")
            
            if not browser_id:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": "Missing required parameter: browser_id"
                    }
                }
            
            if browser_id in browser_operators:
                operator = browser_operators[browser_id]
                await operator.close()
                del browser_operators[browser_id]
                
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "status": "reset",
                        "browser_id": browser_id
                    }
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32602,
                        "message": f"Browser ID not found: {browser_id}"
                    }
                }
        
        elif method == "tools.list":
            # Return the list of available tools
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "browser_operator",
                            "description": "Operates a browser to navigate websites, click elements, and fill forms.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "browser_id": {
                                        "type": "string",
                                        "description": "Optional browser instance ID to use an existing browser. If not provided, a new browser will be created."
                                    },
                                    "instruction": {
                                        "type": "string", 
                                        "description": "The instruction to perform in the browser."
                                    }
                                },
                                "required": ["instruction"]
                            }
                        },
                        {
                            "name": "browser_reset",
                            "description": "Reset (close) a browser instance.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "browser_id": {
                                        "type": "string",
                                        "description": "The browser instance ID to reset."
                                    }
                                },
                                "required": ["browser_id"]
                            }
                        }
                    ]
                }
            }
            
        elif method == "shutdown":
            # Clean up all browsers
            for operator in list(browser_operators.values()):
                try:
                    await operator.close()
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
            browser_operators.clear()
            
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": None
            }
            
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
            
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32000,
                "message": f"Internal error: {str(e)}"
            }
        }

if __name__ == "__main__":
    asyncio.run(main())