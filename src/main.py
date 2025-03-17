#!/usr/bin/env python3

import asyncio
import json
import os
import uuid
from typing import Dict, List, Optional, Union, Any, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from browser_operator import BrowserOperator, BrowserInstance

app = FastAPI()
browser_operators: Dict[str, BrowserOperator] = {}

class MCPMessage(BaseModel):
    role: str
    content: Optional[str] = None
    function_call: Optional[dict] = None
    
class MCPRequest(BaseModel):
    messages: List[MCPMessage]
    tools: List[dict]
    browser_id: Optional[str] = None
    
class MCPResponse(BaseModel):
    role: str = "assistant"
    content: Optional[str] = None
    function_call: Optional[dict] = None
    
@app.post("/chat")
async def handle_chat(request: MCPRequest):
    """Handle incoming chat requests."""
    # Extract the last user message
    user_message = next((m for m in reversed(request.messages) if m.role == "user"), None)
    if not user_message or not user_message.content:
        return JSONResponse(content={"error": "No user message found"}, status_code=400)
    
    # Get or create a browser operator
    browser_id = request.browser_id
    if browser_id and browser_id in browser_operators:
        operator = browser_operators[browser_id]
    else:
        # Create a new browser instance
        browser_id = str(uuid.uuid4())
        operator = BrowserOperator(browser_id)
        browser_operators[browser_id] = operator
        await operator.initialize()
    
    # Process the user message
    result = await operator.process_message(user_message.content)
    
    response = MCPResponse(
        content=f"Browser ID: {browser_id}\n\n{result}"
    )
    
    return response

@app.post("/reset/{browser_id}")
async def reset_browser(browser_id: str):
    """Reset a browser instance."""
    if browser_id in browser_operators:
        operator = browser_operators[browser_id]
        await operator.close()
        del browser_operators[browser_id]
        return {"status": "reset", "browser_id": browser_id}
    return JSONResponse(content={"error": "Browser ID not found"}, status_code=404)

@app.on_event("shutdown")
async def shutdown_event():
    """Close all browser instances on shutdown."""
    for operator in browser_operators.values():
        await operator.close()

def main():
    """Run the server."""
    # Use environment variable for port or default to 9978
    port = int(os.environ.get("BROWSER_OPERATOR_PORT", 9978))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)

if __name__ == "__main__":
    main()