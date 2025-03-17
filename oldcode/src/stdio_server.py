#!/usr/bin/env python3

import asyncio
import json
import logging
import sys
import uuid
from typing import Dict, List, Optional, Any, Tuple

from browser_operator import BrowserOperator

# Configure logging to file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("mcp-operator.log"), logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

# Store browser instances
browser_operators: Dict[str, BrowserOperator] = {}

async def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle an incoming JSON-RPC request."""
    
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    
    logger.info(f"Received request {req_id}: {method} with params {params}")
    
    try:
        if method == "browser_operator":
            return await handle_browser_operator(req_id, params)
        elif method == "browser_reset":
            return await handle_browser_reset(req_id, params)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not found"
                }
            }
    except Exception as e:
        logger.error(f"Error handling request: {e}", exc_info=True)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32000,
                "message": f"Internal error: {str(e)}"
            }
        }

async def handle_browser_operator(req_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle browser_operator method."""
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
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "browser_id": browser_id,
            "output": result
        }
    }

async def handle_browser_reset(req_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle browser_reset method."""
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

async def stdio_server():
    """Run a server that communicates over stdin/stdout."""
    logger.info("Starting stdio MCP server for browser operation")
    
    # Set up reader and writer for stdin/stdout
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    
    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, asyncio.get_event_loop())
    
    # Process JSON-RPC requests over stdin/stdout
    while True:
        try:
            line = await reader.readline()
            if not line:
                break
                
            request = json.loads(line)
            response = await handle_request(request)
            
            # Write the response as a single line of JSON
            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error"
                }
            }
            writer.write((json.dumps(error_response) + "\n").encode())
            await writer.drain()
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": f"Internal error: {str(e)}"
                }
            }
            writer.write((json.dumps(error_response) + "\n").encode())
            await writer.drain()

def main():
    """Main entry point for the stdio server."""
    asyncio.run(stdio_server())

if __name__ == "__main__":
    main()