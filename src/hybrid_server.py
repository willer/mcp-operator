#!/usr/bin/env python3

import asyncio
import json
import logging
import os
import sys
import uuid
from typing import Dict, List, Optional, Any, Tuple

# Configure logging to file only to avoid interfering with stdio
log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp-operator.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file)]
)
logger = logging.getLogger(__name__)

# Import browser operator
try:
    from browser_operator import BrowserOperator
except ImportError:
    from src.browser_operator import BrowserOperator

# Store browser instances
browser_operators: Dict[str, BrowserOperator] = {}

async def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle an incoming JSON-RPC request."""
    
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id")
    
    logger.info(f"Received request {req_id}: {method} with params {params}")
    
    try:
        # MCP initialization method
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {
                        "name": "browser-operator",
                        "version": "0.1.0"
                    },
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
                    }
                }
            }
        # Handle tools.list method
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
                                        "description": "The instruction to perform in the browser, such as 'navigate to google.com', 'click the search button', etc."
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
                
        # MCP shutdown method
        elif method == "shutdown":
            # Close all browser instances
            for operator in list(browser_operators.values()):
                try:
                    await operator.close()
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
            browser_operators.clear()
            
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"status": "ok"}
            }
        # Tool methods
        elif method == "browser_operator":
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
    
    # Print a simple message to signal we're running
    print("Browser Operator MCP Server running on stdio", file=sys.stderr)
    
    # Set up reader and writer for stdin/stdout
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
    
    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, asyncio.get_event_loop())
    
    logger.info("Stdio server setup complete, waiting for input")
    
    # Process JSON-RPC requests over stdin/stdout
    while True:
        try:
            logger.info("Waiting for input...")
            line = await reader.readline()
            if not line:
                logger.info("End of input stream")
                break
                
            logger.info(f"Received line: {line.decode('utf-8').strip()}")
            request = json.loads(line)
            logger.info(f"Parsed request: {request}")
            
            response = await handle_request(request)
            logger.info(f"Sending response: {response}")
            
            # Write the response as a single line of JSON
            response_json = json.dumps(response) + "\n"
            logger.info(f"Encoded response: {response_json.strip()}")
            writer.write(response_json.encode())
            await writer.drain()
            logger.info("Response sent")
            
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

def run_http_server():
    """Run a FastAPI server for HTTP communication."""
    try:
        import uvicorn
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        
        app = FastAPI()
        
        @app.post("/")
        async def handle_jsonrpc(request: Request):
            """Handle JSON-RPC requests over HTTP."""
            try:
                request_data = await request.json()
                response = await handle_request(request_data)
                return JSONResponse(content=response)
            except Exception as e:
                logger.error(f"Error handling HTTP request: {e}", exc_info=True)
                return JSONResponse(
                    status_code=500,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32000,
                            "message": f"Internal server error: {str(e)}"
                        }
                    }
                )
        
        @app.on_event("shutdown")
        async def shutdown_event():
            """Close all browser instances on shutdown."""
            for operator in browser_operators.values():
                try:
                    await operator.close()
                except Exception as e:
                    logger.error(f"Error closing browser: {e}")
        
        # Get port from environment or use default
        port = int(os.environ.get("BROWSER_OPERATOR_PORT", "9978"))
        
        # Start the server
        uvicorn.run(app, host="0.0.0.0", port=port)
        
    except ImportError as e:
        logger.error(f"Failed to import HTTP server dependencies: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error running HTTP server: {e}", exc_info=True)
        sys.exit(1)

def detect_mode():
    """Detect which mode to run in based on environment variables."""
    transport = os.environ.get("MCP_TRANSPORT", "").lower()
    
    if transport == "stdio":
        return "stdio"
    elif transport == "http":
        return "http"
    
    # Check if port is defined as a signal for HTTP mode
    if "BROWSER_OPERATOR_PORT" in os.environ or "PORT" in os.environ:
        return "http"
    
    # Check for environment variables that might indicate stdio mode
    if "MCP_STDIO" in os.environ or "CLAUDE_MCP_STDIO" in os.environ:
        return "stdio"
    
    # Default to stdio if UVICORN_FD is not set (uvicorn sets this for HTTP servers)
    if "UVICORN_FD" not in os.environ:
        return "stdio"
    
    # Default fallback
    return "http"

def main():
    """Main entry point for the hybrid server."""
    mode = detect_mode()
    
    logger.info(f"Starting Browser Operator MCP in {mode} mode")
    
    if mode == "stdio":
        asyncio.run(stdio_server())
    else:
        run_http_server()

if __name__ == "__main__":
    main()