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

# Note: We should never use print() statements in this codebase.
# Always use the logger module for any diagnostic output.
# Ensure we don't output anything to stdout/stderr in the logger
for handler in logging.root.handlers[:]:
    if isinstance(handler, logging.StreamHandler):
        logging.root.removeHandler(handler)

# Create our logger that only writes to file
logger = logging.getLogger('mcp-operator')

# Import the rewired browser operator that uses the CUA implementation
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
                    "project_name": {"type": "string", "description": "Project name for browser state identification and persistence"},
                },
                "required": ["project_name"],
            },
        ),
        types.Tool(
            name="navigate-browser",
            description="Navigate to a URL in the browser (returns a job_id for tracking)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["project_name", "url"],
            },
        ),
        types.Tool(
            name="operate-browser",
            description="Operate the browser based on a natural language instruction (returns a job_id for tracking)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "instruction": {"type": "string"},
                },
                "required": ["project_name", "instruction"],
            },
        ),
        types.Tool(
            name="close-browser",
            description="Close a browser instance (returns a job_id for tracking)",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                },
                "required": ["project_name"],
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
    
    For long-running browser operations, we use a job-based approach:
    1. Client calls a tool like "operate-browser"
    2. Server immediately returns a job_id
    3. Operation continues in the background
    4. Client can poll using get-job-status to check when done
    """
    logger.info(f"Tool requested: {name} with arguments: {arguments}")
    
    if not arguments and name not in ["list-jobs"]:
        raise ValueError("Missing arguments")
    
    # Helper to format job status for response
    def format_job_status(job_info: Dict[str, Any]) -> List[types.TextContent]:
        """Format job info into a nice response"""
        job_id = job_info["id"]
        status = job_info["status"]
        created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job_info["created_at"]))
        updated = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(job_info["updated_at"]))
        
        # Build response text
        result_text = f"Job ID: {job_id}\nStatus: {status}\nCreated: {created}\nUpdated: {updated}\n"
        
        # Add operation details
        result_text += f"Operation: {job_info['operation_type']}\n"
        result_text += f"Description: {job_info['description']}\n"
        
        # Add error message if there is one
        if job_info.get("error"):
            result_text += f"Error: {job_info['error']}\n"
            
        # Add metadata if available
        if job_info.get("metadata"):
            result_text += "\nMetadata:\n"
            for key, value in job_info["metadata"].items():
                result_text += f"  {key}: {value}\n"
        
        response = [
            types.TextContent(
                type="text",
                text=result_text,
            )
        ]
        
        # If job is complete and has result with screenshot, add it
        if status == JobStatus.COMPLETED and job_info.get("result"):
            result = job_info["result"]
            if isinstance(result, list) and len(result) > 0:
                # Add all text content first
                for item in result:
                    if isinstance(item, dict) and item.get("type") == "text":
                        response.append(
                            types.TextContent(
                                type="text",
                                text=item["text"],
                            )
                        )
                
                # Then add the first image if available (to keep response size reasonable)
                for item in result:
                    if isinstance(item, dict) and item.get("type") == "image" and item.get("data"):
                        try:
                            response.append(
                                types.ImageContent(
                                    type="image",
                                    data=item["data"],
                                    mimeType=item.get("mimeType", "image/png"),
                                )
                            )
                            break  # Only add the first image
                        except Exception as e:
                            response.append(
                                types.TextContent(
                                    type="text",
                                    text=f"Could not process image: {str(e)}",
                                )
                            )
        
        return response
    
    # Job management tools
    if name == "get-job-status":
        job_id = arguments.get("job_id")
        if not job_id:
            raise ValueError("Missing job_id parameter")
        
        job_info = job_manager.get_job(job_id)
        if not job_info:
            return [
                types.TextContent(
                    type="text",
                    text=f"Job with ID {job_id} not found",
                )
            ]
        
        return format_job_status(job_info)
    
    elif name == "list-jobs":
        limit = arguments.get("limit", 10) if arguments else 10
        jobs = job_manager.list_jobs(limit=limit)
        
        if not jobs:
            return [
                types.TextContent(
                    type="text",
                    text="No jobs found",
                )
            ]
        
        # Create a summary list
        summary_text = f"Recent Jobs (showing {len(jobs)} of {len(job_manager.jobs)}):\n\n"
        for job in jobs:
            job_time = time.strftime("%H:%M:%S", time.localtime(job["updated_at"]))
            summary_text += f"• {job['id']} - {job['status']} - {job['operation_type']} - {job['description']} ({job_time})\n"
        
        return [
            types.TextContent(
                type="text",
                text=summary_text,
            )
        ]
    
    # Note management tool
    elif name == "add-note":
        note_name = arguments.get("name")
        note_content = arguments.get("content")
        
        if not note_name or not note_content:
            raise ValueError("Missing name or content parameters")
        
        notes[note_name] = note_content
        
        return [
            types.TextContent(
                type="text",
                text=f"Note '{note_name}' added successfully",
            )
        ]
    
    # Browser operation tools - these now create jobs and return immediately
    elif name == "create-browser":
        project_name = arguments.get("project_name")
        if not project_name:
            raise ValueError("Missing project_name")
        
        # Check if browser already exists
        if project_name in browser_operators:
            return [
                types.TextContent(
                    type="text",
                    text=f"Browser for project '{project_name}' already exists. Close the existing browser first or use a different project name.",
                )
            ]
        
        # Create a new job for the browser creation operation
        job_id = job_manager.create_job(
            operation_type="create-browser",
            description=f"Create browser instance for project: {project_name}",
            project_name=project_name
        )
        
        # Define the async function that will run in the background
        async def create_browser_job():
            try:
                # Create a new browser operator with project-based persistence
                browser_operator = BrowserOperator(project_name)
                success = await browser_operator.initialize()
                
                if not success:
                    return [{
                        "type": "text",
                        "text": f"Error creating browser for project: {project_name}. Check logs for details.",
                    }]
                
                browser_operators[project_name] = browser_operator
                
                # Take initial screenshot to show
                screenshot = await browser_operator.browser_instance.take_screenshot()
                
                response = [
                    {
                        "type": "text",
                        "text": f"Created browser for project: {project_name}",
                    }
                ]
                
                if screenshot:
                    try:
                        response.append({
                            "type": "image",
                            "data": screenshot,  # Already base64-encoded
                            "mimeType": "image/png",
                        })
                    except Exception as e:
                        response.append({
                            "type": "text",
                            "text": f"Could not process screenshot: {str(e)}",
                        })
                else:
                    response.append({
                        "type": "text",
                        "text": "Could not take initial screenshot.",
                    })
                    
                return response
            except Exception as e:
                logger.error(f"Error in create-browser job: {str(e)}")
                return [{
                    "type": "text",
                    "text": f"Error creating browser: {str(e)}",
                }]
        
        # Start the job in the background without waiting for it
        asyncio.create_task(job_manager.run_job(job_id, create_browser_job()))
        
        # Return immediate response with job ID
        return [
            types.TextContent(
                type="text",
                text=f"Browser creation for project '{project_name}' started. Use get-job-status to check progress.\nJob ID: {job_id}",
            )
        ]
    
    elif name == "navigate-browser":
        project_name = arguments.get("project_name")
        url = arguments.get("url")
        
        if not project_name or not url:
            raise ValueError("Missing project_name or url")
        
        if project_name not in browser_operators:
            raise ValueError(f"Browser for project '{project_name}' not found")
        
        browser_operator = browser_operators[project_name]
        
        # Create a new job for the navigation operation
        job_id = job_manager.create_job(
            operation_type="navigate-browser",
            description=f"Navigate to: {url}",
            project_name=project_name,
            url=url
        )
        
        # Define the async function that will run in the background
        async def navigate_browser_job():
            try:
                result = await browser_operator.navigate(url)
                
                # Create text response with navigation results
                response_text = result.get("text", f"Navigated to {url}")
                
                # Add error information if available
                if "error" in result:
                    response_text = f"Error navigating to {url}: {result['error']}\n{response_text}"
                
                response = [
                    {
                        "type": "text",
                        "text": response_text,
                    }
                ]
                
                if "screenshot" in result and result["screenshot"]:
                    try:
                        response.append({
                            "type": "image",
                            "data": result["screenshot"],
                            "mimeType": "image/png",
                        })
                    except Exception as e:
                        response.append({
                            "type": "text",
                            "text": f"Could not process screenshot: {str(e)}",
                        })
                else:
                    response.append({
                        "type": "text",
                        "text": "Could not take screenshot after navigation.",
                    })
                    
                return response
            except Exception as e:
                logger.error(f"Error in navigate-browser job: {str(e)}")
                return [{
                    "type": "text",
                    "text": f"Error navigating browser: {str(e)}",
                }]
        
        # Start the job in the background without waiting for it
        asyncio.create_task(job_manager.run_job(job_id, navigate_browser_job()))
        
        # Return immediate response with job ID
        return [
            types.TextContent(
                type="text",
                text=f"Navigation for project '{project_name}' started. Use get-job-status to check progress.\nJob ID: {job_id}",
            )
        ]
    
    elif name == "operate-browser":
        project_name = arguments.get("project_name")
        instruction = arguments.get("instruction")
        
        if not project_name or not instruction:
            raise ValueError("Missing project_name or instruction")
        
        if project_name not in browser_operators:
            raise ValueError(f"Browser for project '{project_name}' not found")
        
        browser_operator = browser_operators[project_name]
        
        # Create a new job for the operation 
        job_id = job_manager.create_job(
            operation_type="operate-browser",
            description=f"Instruction: {instruction[:50]}{'...' if len(instruction) > 50 else ''}",
            project_name=project_name,
            instruction=instruction
        )
        
        # Define the async function that will run in the background
        async def operate_browser_job():
            try:
                result = await browser_operator.process_message(instruction)
                
                # Get number of actions executed to add to response
                actions_executed = result.get("actions_executed", 0)
                
                # Create response text with action count info if needed
                result_text = result.get("text", "Operation completed")
                
                # Add error information if available
                if "error" in result:
                    result_text = f"Error processing instruction: {result['error']}\n{result_text}"
                
                if actions_executed == 0:
                    # Add a note about no actions being performed
                    result_text = "⚠️ No browser actions were performed. Please try a different instruction or provide more details.\n\n" + result_text
                
                response = [
                    {
                        "type": "text",
                        "text": result_text,
                    }
                ]
                
                if "screenshot" in result and result["screenshot"]:
                    try:
                        response.append({
                            "type": "image",
                            "data": result["screenshot"],
                            "mimeType": "image/png",
                        })
                    except Exception as e:
                        response.append({
                            "type": "text",
                            "text": f"Could not process screenshot: {str(e)}",
                        })
                
                return response
            except Exception as e:
                logger.error(f"Error in operate-browser job: {str(e)}")
                return [{
                    "type": "text",
                    "text": f"Error operating browser: {str(e)}",
                }]
        
        # Start the job in the background without waiting for it
        asyncio.create_task(job_manager.run_job(job_id, operate_browser_job()))
        
        # Return immediate response with job ID
        return [
            types.TextContent(
                type="text",
                text=f"Browser operation for project '{project_name}' started. Use get-job-status to check progress.\nJob ID: {job_id}",
            )
        ]
    
    elif name == "close-browser":
        project_name = arguments.get("project_name")
        
        if not project_name:
            raise ValueError("Missing project_name")
        
        if project_name not in browser_operators:
            raise ValueError(f"Browser for project '{project_name}' not found")
        
        # Create a new job for closing the browser 
        job_id = job_manager.create_job(
            operation_type="close-browser",
            description=f"Close browser for project: {project_name}",
            project_name=project_name
        )
        
        # Define the async function that will run in the background
        async def close_browser_job():
            try:
                browser_operator = browser_operators.pop(project_name)
                await browser_operator.close()
                
                return [
                    {
                        "type": "text",
                        "text": f"Closed browser for project: {project_name}",
                    }
                ]
            except Exception as e:
                logger.error(f"Error in close-browser job: {str(e)}")
                return [{
                    "type": "text",
                    "text": f"Error closing browser: {str(e)}",
                }]
        
        # Start the job in the background without waiting for it
        asyncio.create_task(job_manager.run_job(job_id, close_browser_job()))
        
        # Return immediate response with job ID
        return [
            types.TextContent(
                type="text",
                text=f"Browser closing for project '{project_name}' started. Use get-job-status to check progress.\nJob ID: {job_id}",
            )
        ]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

# We are not implementing our own JSON-RPC server handlers - we're using the MCP SDK
# This was removed as it was interfering with the proper MCP JSON-RPC handlers

async def main():
    # Use MCP's stdio server
    try:
        # Start job manager cleanup task for background maintenance
        logger.info("Starting job manager cleanup task")
        job_manager.start_cleanup_task()
        
        # For development, this logging will help debug the errors
        logger.info("Starting MCP server")
        
        # Make sure we're not using any custom stdout/stderr handlers that could break the MCP protocol
        import sys
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        
        # Run the MCP server with standard IO
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
        
        # Close any active browsers
        for project_name, browser_op in browser_operators.items():
            try:
                asyncio.create_task(browser_op.close())
                logger.info(f"Closed browser for project {project_name} during shutdown")
            except Exception as close_err:
                logger.error(f"Error closing browser {project_name}: {str(close_err)}")
                
        # Use an exit code to indicate error
        sys.exit(1)