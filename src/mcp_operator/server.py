import asyncio
import base64
import sys
import logging
import json
import os
import uuid
import time
from typing import Dict, Any, Optional, List, Tuple

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

# Set up logging to file to avoid stdout pollution
log_dir = os.path.join(os.path.expanduser("~"), ".mcp-operator-logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "mcp-operator.log")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
    ]
)
logger = logging.getLogger('mcp-operator')

from .browser import BrowserOperator

# Store notes as a simple key-value dict to demonstrate state management
notes: dict[str, str] = {}
# Initialize browser operator
browser_operators: dict[str, BrowserOperator] = {}

# Job tracking system
class JobStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.job_tasks: Dict[str, asyncio.Task] = {}
        self.cleanup_task = None
        
    def start_cleanup_task(self):
        """Start a background task to clean up old jobs"""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._cleanup_old_jobs())
        
    async def _cleanup_old_jobs(self):
        """Periodically clean up old completed jobs"""
        while True:
            try:
                current_time = time.time()
                to_delete = []
                
                for job_id, job_info in self.jobs.items():
                    # Remove jobs that are complete/failed and older than 1 hour
                    if (job_info["status"] in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.TIMEOUT] and
                        current_time - job_info["updated_at"] > 3600):
                        to_delete.append(job_id)
                
                for job_id in to_delete:
                    del self.jobs[job_id]
                    logger.info(f"Cleaned up old job: {job_id}")
                
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Error in job cleanup: {str(e)}")
                await asyncio.sleep(60)  # Wait and retry
    
    def create_job(self, operation_type: str, description: str, **metadata) -> str:
        """Create a new job and return its ID"""
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            "id": job_id,
            "operation_type": operation_type,
            "description": description,
            "status": JobStatus.PENDING,
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time(),
            "metadata": metadata
        }
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job information by ID"""
        return self.jobs.get(job_id)
    
    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent jobs, newest first"""
        sorted_jobs = sorted(
            self.jobs.values(), 
            key=lambda x: x["updated_at"], 
            reverse=True
        )
        return sorted_jobs[:limit]
    
    def update_job_status(self, job_id: str, status: str) -> None:
        """Update a job's status"""
        if job_id in self.jobs:
            self.jobs[job_id]["status"] = status
            self.jobs[job_id]["updated_at"] = time.time()
    
    def set_job_result(self, job_id: str, result: Any) -> None:
        """Set a job's result and mark as completed"""
        if job_id in self.jobs:
            self.jobs[job_id]["result"] = result
            self.jobs[job_id]["status"] = JobStatus.COMPLETED
            self.jobs[job_id]["updated_at"] = time.time()
    
    def set_job_error(self, job_id: str, error: str) -> None:
        """Set a job's error and mark as failed"""
        if job_id in self.jobs:
            self.jobs[job_id]["error"] = error
            self.jobs[job_id]["status"] = JobStatus.FAILED
            self.jobs[job_id]["updated_at"] = time.time()
    
    def set_job_timeout(self, job_id: str, reason: str) -> None:
        """Mark a job as timed out"""
        if job_id in self.jobs:
            self.jobs[job_id]["error"] = reason
            self.jobs[job_id]["status"] = JobStatus.TIMEOUT
            self.jobs[job_id]["updated_at"] = time.time()
    
    async def run_job(self, job_id: str, coroutine) -> None:
        """Run a job as a background task"""
        if job_id not in self.jobs:
            logger.error(f"Attempting to run non-existent job: {job_id}")
            return
        
        self.update_job_status(job_id, JobStatus.RUNNING)
        
        try:
            # Start the task and store it for management
            task = asyncio.create_task(coroutine)
            self.job_tasks[job_id] = task
            
            # Wait for it to complete
            result = await task
            
            # Update the job with the result
            self.set_job_result(job_id, result)
            logger.info(f"Job {job_id} completed successfully")
            
        except asyncio.TimeoutError:
            self.set_job_timeout(job_id, "Operation timed out")
            logger.warning(f"Job {job_id} timed out")
            
        except asyncio.CancelledError:
            self.set_job_error(job_id, "Operation was cancelled")
            logger.warning(f"Job {job_id} was cancelled")
            
        except Exception as e:
            self.set_job_error(job_id, str(e))
            logger.error(f"Job {job_id} failed with error: {str(e)}")
            
        finally:
            # Clean up the task reference
            if job_id in self.job_tasks:
                del self.job_tasks[job_id]

# Initialize the job manager
job_manager = JobManager()

server = Server("mcp-operator")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available note resources.
    Each note is exposed as a resource with a custom note:// URI scheme.
    """
    return [
        types.Resource(
            uri=AnyUrl(f"note://internal/{name}"),
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific note's content by its URI.
    The note name is extracted from the URI host component.
    """
    if uri.scheme != "note":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    name = uri.path
    if name is not None:
        name = name.lstrip("/")
        return notes[name]
    raise ValueError(f"Note not found: {name}")

@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    Each prompt can have optional arguments to customize its behavior.
    """
    return [
        types.Prompt(
            name="summarize-notes",
            description="Creates a summary of all notes",
            arguments=[
                types.PromptArgument(
                    name="style",
                    description="Style of the summary (brief/detailed)",
                    required=False,
                )
            ],
        )
    ]

@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate a prompt by combining arguments with server state.
    The prompt includes all current notes and can be customized via arguments.
    """
    if name != "summarize-notes":
        raise ValueError(f"Unknown prompt: {name}")

    style = (arguments or {}).get("style", "brief")
    detail_prompt = " Give extensive details." if style == "detailed" else ""

    return types.GetPromptResult(
        description="Summarize the current notes",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n"
                    + "\n".join(
                        f"- {name}: {content}"
                        for name, content in notes.items()
                    ),
                ),
            )
        ],
    )

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        # Browser operation tools with async job support
        types.Tool(
            name="create-browser",
            description="Create a new browser instance (returns a job_id for tracking)",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                },
                "required": ["browser_id"],
            },
        ),
        types.Tool(
            name="navigate-browser",
            description="Navigate to a URL in the browser (returns a job_id for tracking)",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["browser_id", "url"],
            },
        ),
        types.Tool(
            name="operate-browser",
            description="Operate the browser based on a natural language instruction (returns a job_id for tracking)",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                    "instruction": {"type": "string"},
                },
                "required": ["browser_id", "instruction"],
            },
        ),
        types.Tool(
            name="close-browser",
            description="Close a browser instance (returns a job_id for tracking)",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                },
                "required": ["browser_id"],
            },
        ),
        
        # Job management tools
        types.Tool(
            name="get-job-status",
            description="Get the status and result of a job by its ID",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                },
                "required": ["job_id"],
            },
        ),
        types.Tool(
            name="list-jobs",
            description="List recent browser operation jobs",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "number", "description": "Maximum number of jobs to return (default: 10)"},
                },
                "required": [],
            },
        ),
        
        # Note management tools (original functionality)
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    logger.info(f"Tool requested: {name} with arguments: {arguments}")
    
    if not arguments:
        raise ValueError("Missing arguments")
    
    # Create a wrapper to handle timeouts
    async def execute_with_timeout(coroutine, timeout_seconds=30):
        try:
            return await asyncio.wait_for(coroutine, timeout=timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(f"Tool execution timed out after {timeout_seconds} seconds: {name}")
            return [
                types.TextContent(
                    type="text",
                    text=f"Operation timed out after {timeout_seconds} seconds. The request to {name} may have been too complex or encountered delays.",
                )
            ]
            
    if name == "create-browser":
        browser_id = arguments.get("browser_id")
        if not browser_id:
            raise ValueError("Missing browser_id")
        
        logger.info(f"Creating browser with ID: {browser_id}")
        
        async def create_browser_with_response():
            # Create a new browser operator
            browser_operator = BrowserOperator(browser_id)
            await browser_operator.initialize()
            browser_operators[browser_id] = browser_operator
            
            # Take initial screenshot to show
            screenshot = await browser_operator.browser_instance.take_screenshot()
            
            response = [
                types.TextContent(
                    type="text",
                    text=f"Created browser with ID: {browser_id}",
                )
            ]
            
            if screenshot:
                try:
                    # The data URL format should be correct without adding the prefix
                    response.append(types.ImageContent(
                        type="image",
                        data=screenshot,  # The screenshot is already base64-encoded
                        mimeType="image/png",
                    ))
                except Exception as e:
                    response.append(types.TextContent(
                        type="text",
                        text=f"Could not process screenshot: {str(e)}",
                    ))
            else:
                response.append(types.TextContent(
                    type="text",
                    text="Could not take initial screenshot.",
                ))
                
            return response
            
        return await execute_with_timeout(create_browser_with_response(), 40)
    
    elif name == "navigate-browser":
        browser_id = arguments.get("browser_id")
        url = arguments.get("url")
        
        if not browser_id or not url:
            raise ValueError("Missing browser_id or url")
        
        if browser_id not in browser_operators:
            raise ValueError(f"Browser with ID {browser_id} not found")
        
        browser_operator = browser_operators[browser_id]
        
        # Use special timeout for yahoo
        timeout_seconds = 45 if "yahoo.com" in url.lower() else 30
        logger.info(f"Navigating to {url} with {timeout_seconds}s timeout")
        
        # Execute navigation with timeout
        async def navigate_with_response():
            result = await browser_operator.navigate(url)
            
            response = [
                types.TextContent(
                    type="text",
                    text=result["text"],
                )
            ]
            
            if "screenshot" in result and result["screenshot"]:
                try:
                    response.append(types.ImageContent(
                        type="image",
                        data=result["screenshot"],
                        mimeType="image/png",
                    ))
                except Exception as e:
                    response.append(types.TextContent(
                        type="text",
                        text=f"Could not process screenshot: {str(e)}",
                    ))
            else:
                response.append(types.TextContent(
                    type="text",
                    text="Could not take screenshot after navigation.",
                ))
                
            return response
            
        return await execute_with_timeout(navigate_with_response(), timeout_seconds)
    
    elif name == "operate-browser":
        browser_id = arguments.get("browser_id")
        instruction = arguments.get("instruction")
        
        if not browser_id or not instruction:
            raise ValueError("Missing browser_id or instruction")
        
        if browser_id not in browser_operators:
            raise ValueError(f"Browser with ID {browser_id} not found")
        
        browser_operator = browser_operators[browser_id]
        
        # CUA operations can take longer, use 90 second timeout
        logger.info(f"Processing browser operation: '{instruction}'")
        
        async def operate_with_response():
            result = await browser_operator.process_message(instruction)
            
            # Get number of actions executed to add to response
            actions_executed = result.get("actions_executed", 0)
            
            # Create response text with action count info if needed
            result_text = result["text"]
            if actions_executed == 0:
                # Add a note about no actions being performed
                result_text = "⚠️ No browser actions were performed. Please try a different instruction or provide more details.\n\n" + result_text
            
            responses = [
                types.TextContent(
                    type="text",
                    text=result_text,
                )
            ]
            
            if "screenshot" in result and result["screenshot"]:
                try:
                    responses.append(
                        types.ImageContent(
                            type="image",
                            data=result["screenshot"],
                            mimeType="image/png",
                        )
                    )
                except Exception as e:
                    responses.append(
                        types.TextContent(
                            type="text",
                            text=f"Could not process screenshot: {str(e)}",
                        )
                    )
            
            return responses
        
        return await execute_with_timeout(operate_with_response(), 90)
    
    elif name == "close-browser":
        browser_id = arguments.get("browser_id")
        
        if not browser_id:
            raise ValueError("Missing browser_id")
        
        if browser_id not in browser_operators:
            raise ValueError(f"Browser with ID {browser_id} not found")
        
        logger.info(f"Closing browser with ID: {browser_id}")
        
        async def close_browser_with_response():
            browser_operator = browser_operators.pop(browser_id)
            await browser_operator.close()
            
            return [
                types.TextContent(
                    type="text",
                    text=f"Closed browser with ID: {browser_id}",
                )
            ]
            
        return await execute_with_timeout(close_browser_with_response(), 15)
    
    else:
        raise ValueError(f"Unknown tool: {name}")

# Simple message formatter that ensures valid JSON with Content-Length header
class JsonRpcFormatter:
    @staticmethod
    def format_message(message):
        message_json = json.dumps(message)
        length = len(message_json)
        return f"Content-Length: {length}\r\n\r\n{message_json}"

# Simple clean wrapper for the stdio server
class SafeStdioServer:
    def __init__(self):
        self.request_counter = 0
        self.pending_responses = {}
        
    async def run(self):
        while True:
            try:
                # Read messages from stdin
                message = await self._read_message()
                if not message:
                    continue
                    
                # Process the message
                response = await self._process_message(message)
                if response:
                    # Send the response
                    await self._write_message(response)
            except Exception as e:
                logger.error(f"Error in stdio server: {str(e)}")
                # Try to recover
                await asyncio.sleep(0.1)
    
    async def _read_message(self):
        # Read Content-Length header
        header = await self._read_line()
        if not header:
            return None
            
        if not header.startswith("Content-Length:"):
            logger.warning(f"Invalid header: {header}")
            return None
            
        content_length = int(header.split(":")[1].strip())
        
        # Skip empty line
        await self._read_line()
        
        # Read content
        content = await self._read_content(content_length)
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing message: {str(e)}")
            return None
    
    async def _read_line(self):
        line = ""
        while True:
            char = sys.stdin.buffer.read(1).decode('utf-8')
            if not char:
                return None
            if char == '\r':
                next_char = sys.stdin.buffer.read(1).decode('utf-8')
                if next_char == '\n':
                    return line
            elif char == '\n':
                return line
            else:
                line += char
    
    async def _read_content(self, length):
        content = sys.stdin.buffer.read(length).decode('utf-8')
        return content
    
    async def _process_message(self, message):
        # Extract information from message
        message_id = message.get("id")
        message_method = message.get("method")
        message_params = message.get("params", {})
        
        # Process initialization
        if message_method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": {
                    "serverInfo": {
                        "name": "mcp-operator",
                        "version": "0.1.0"
                    },
                    "capabilities": {
                        "listResourcesProvider": True,
                        "readResourceProvider": True,
                        "listPromptsProvider": True,
                        "getPromptProvider": True,
                        "toolProvider": True,
                        "supportsNotifications": True
                    }
                }
            }
            
        # Process other methods
        # Add more handlers for other methods
        
        # Default response
        return {
            "jsonrpc": "2.0",
            "id": message_id,
            "error": {
                "code": -32601,
                "message": f"Method not implemented: {message_method}"
            }
        }
    
    async def _write_message(self, message):
        # Format the message
        formatted_message = JsonRpcFormatter.format_message(message)
        sys.stdout.buffer.write(formatted_message.encode('utf-8'))
        sys.stdout.buffer.flush()

async def main():
    # Use MCP's stdio server
    try:
        # Start job manager cleanup task for background maintenance
        logger.info("Starting job manager cleanup task")
        job_manager.start_cleanup_task()
        
        # For development, this logging will help debug the errors
        logger.info("Starting MCP server")
        
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            logger.info("MCP stdio server created")
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp-operator",
                    server_version="0.1.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )
    except Exception as e:
        # Log the error and exit gracefully
        import traceback
        error_text = f"Error in MCP server: {str(e)}\n{traceback.format_exc()}"
        logger.critical(error_text)
        
        # Don't output to stdout/stderr to avoid breaking the JSON protocol
        
        # Close any active browsers
        for browser_id, browser_op in browser_operators.items():
            try:
                asyncio.create_task(browser_op.close())
                logger.info(f"Closed browser {browser_id} during shutdown")
            except Exception as close_err:
                logger.error(f"Error closing browser {browser_id}: {str(close_err)}")
                
        # Use an exit code to indicate error
        sys.exit(1)