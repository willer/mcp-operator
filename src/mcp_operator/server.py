#!/usr/bin/env python3
"""
MCP Server implementation for the Browser Operator
"""

import os
import sys
import json
import asyncio
import signal
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple
import logging
from pathlib import Path

# Set up logging to avoid interfering with MCP protocol
log_dir = Path(os.environ.get("MCP_LOG_DIR", "logs"))
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"mcp_server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure logging to file only (no stdout)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        # No stream handler to avoid interfering with MCP
    ]
)

logger = logging.getLogger("mcp-server")

# Import our browser operator
from mcp_operator.browser import BrowserOperator

class MCPServer:
    """MCP Server implementation for Browser Operator"""
    
    def __init__(self):
        """Initialize the MCP server"""
        # Dictionary of browser operators keyed by project name
        self.operators: Dict[str, BrowserOperator] = {}
        
        # Request ID counter
        self.request_counter = 0
        
        logger.info("MCP Server initialized")
    
    def _get_operator(self, project_name: str) -> BrowserOperator:
        """Get or create a browser operator for a project
        
        Args:
            project_name: Name of the project
            
        Returns:
            BrowserOperator instance
        """
        if project_name not in self.operators:
            logger.info(f"Creating new operator for project: {project_name}")
            self.operators[project_name] = BrowserOperator(project_name)
        
        return self.operators[project_name]
    
    def _generate_request_id(self) -> str:
        """Generate a unique request ID
        
        Returns:
            Request ID string
        """
        self.request_counter += 1
        return f"mcp-req-{self.request_counter}"
    
    def _generate_error_response(self, request_id: str, error_message: str, error_code: int = -32000) -> Dict[str, Any]:
        """Generate a JSON-RPC error response
        
        Args:
            request_id: ID of the request
            error_message: Error message
            error_code: JSON-RPC error code
            
        Returns:
            JSON-RPC error response dict
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": error_code,
                "message": error_message
            }
        }
    
    def _generate_success_response(self, request_id: str, result: Any) -> Dict[str, Any]:
        """Generate a JSON-RPC success response
        
        Args:
            request_id: ID of the request
            result: Result data
            
        Returns:
            JSON-RPC success response dict
        """
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }
    
    async def dispatch_method(self, method: str, params: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        """Dispatch a method call to the appropriate handler
        
        Args:
            method: Method name to call
            params: Method parameters
            request_id: ID of this request
            
        Returns:
            JSON-RPC response dict
        """
        # Map method names to handler functions
        method_map = {
            "mcp__browser-operator__create-browser": self.handle_create_browser,
            "mcp__browser-operator__navigate-browser": self.handle_navigate_browser,
            "mcp__browser-operator__operate-browser": self.handle_operate_browser,
            "mcp__browser-operator__close-browser": self.handle_close_browser,
            "mcp__browser-operator__get-job-status": self.handle_get_job_status,
            "mcp__browser-operator__list-jobs": self.handle_list_jobs,
            "mcp__browser-operator__add-note": self.handle_add_note,
            
            # Browser tools
            "mcp__browser-tools__getConsoleLogs": self.handle_get_console_logs,
            "mcp__browser-tools__getConsoleErrors": self.handle_get_console_errors,
            "mcp__browser-tools__getNetworkErrors": self.handle_get_network_errors,
            "mcp__browser-tools__getNetworkLogs": self.handle_get_network_logs,
            "mcp__browser-tools__takeScreenshot": self.handle_take_screenshot,
            "mcp__browser-tools__getSelectedElement": self.handle_get_selected_element,
            "mcp__browser-tools__wipeLogs": self.handle_wipe_logs,
            
            # Audit tools
            "mcp__browser-tools__runAccessibilityAudit": self.handle_run_accessibility_audit,
            "mcp__browser-tools__runPerformanceAudit": self.handle_run_performance_audit,
            "mcp__browser-tools__runSEOAudit": self.handle_run_seo_audit,
            "mcp__browser-tools__runNextJSAudit": self.handle_run_nextjs_audit,
            "mcp__browser-tools__runBestPracticesAudit": self.handle_run_best_practices_audit,
            "mcp__browser-tools__runDebuggerMode": self.handle_run_debugger_mode,
            "mcp__browser-tools__runAuditMode": self.handle_run_audit_mode
        }
        
        # Check if method exists
        if method not in method_map:
            logger.error(f"Unknown method: {method}")
            return self._generate_error_response(
                request_id,
                f"Method not found: {method}",
                -32601  # Method not found error code
            )
        
        # Call the handler
        try:
            handler = method_map[method]
            result = await handler(params)
            return self._generate_success_response(request_id, result)
        except Exception as e:
            logger.exception(f"Error handling method: {method}")
            return self._generate_error_response(
                request_id,
                f"Error executing method: {str(e)}"
            )
    
    async def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a JSON-RPC request
        
        Args:
            request_data: JSON-RPC request data
            
        Returns:
            JSON-RPC response dict
        """
        # Validate JSON-RPC request
        if "jsonrpc" not in request_data or request_data["jsonrpc"] != "2.0":
            logger.error("Invalid JSON-RPC version")
            return self._generate_error_response(
                request_data.get("id", ""),
                "Invalid JSON-RPC version",
                -32600  # Invalid request error code
            )
        
        if "method" not in request_data:
            logger.error("Missing method field")
            return self._generate_error_response(
                request_data.get("id", ""),
                "Missing method field",
                -32600  # Invalid request error code
            )
        
        # Extract request data
        method = request_data["method"]
        params = request_data.get("params", {})
        request_id = request_data.get("id", self._generate_request_id())
        
        logger.info(f"Request: {request_id} - {method}")
        logger.debug(f"Params: {params}")
        
        # Dispatch to method handler
        response = await self.dispatch_method(method, params, request_id)
        
        logger.info(f"Response: {request_id} - {method} - {'Success' if 'result' in response else 'Error'}")
        return response
    
    # Browser operator handlers
    
    async def handle_create_browser(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle create-browser request
        
        Args:
            params: Request parameters
            
        Returns:
            Response data
        """
        project_name = params.get("project_name", "")
        if not project_name:
            logger.error("Missing project_name parameter")
            raise ValueError("Missing project_name parameter")
        
        operator = self._get_operator(project_name)
        return await operator.create_browser()
    
    async def handle_navigate_browser(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle navigate-browser request
        
        Args:
            params: Request parameters
            
        Returns:
            Response data
        """
        project_name = params.get("project_name", "")
        url = params.get("url", "")
        
        if not project_name:
            logger.error("Missing project_name parameter")
            raise ValueError("Missing project_name parameter")
        
        if not url:
            logger.error("Missing url parameter")
            raise ValueError("Missing url parameter")
        
        operator = self._get_operator(project_name)
        return await operator.navigate_browser(url)
    
    async def handle_operate_browser(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle operate-browser request
        
        Args:
            params: Request parameters
            
        Returns:
            Response data
        """
        project_name = params.get("project_name", "")
        instruction = params.get("instruction", "")
        
        if not project_name:
            logger.error("Missing project_name parameter")
            raise ValueError("Missing project_name parameter")
        
        if not instruction:
            logger.error("Missing instruction parameter")
            raise ValueError("Missing instruction parameter")
        
        operator = self._get_operator(project_name)
        return await operator.operate_browser(instruction)
    
    async def handle_close_browser(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle close-browser request
        
        Args:
            params: Request parameters
            
        Returns:
            Response data
        """
        project_name = params.get("project_name", "")
        
        if not project_name:
            logger.error("Missing project_name parameter")
            raise ValueError("Missing project_name parameter")
        
        operator = self._get_operator(project_name)
        result = await operator.close()
        
        # Remove the operator from our mapping
        if project_name in self.operators:
            del self.operators[project_name]
        
        return result
    
    async def handle_get_job_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle get-job-status request
        
        Args:
            params: Request parameters
            
        Returns:
            Response data with job status
        """
        job_id = params.get("job_id", "")
        
        if not job_id:
            logger.error("Missing job_id parameter")
            raise ValueError("Missing job_id parameter")
        
        # Search for the job in all operators
        for project_name, operator in self.operators.items():
            if job_id in operator.jobs:
                return operator.get_job_status(job_id)
        
        # Job not found
        logger.error(f"Job not found: {job_id}")
        return {"error": f"Job not found: {job_id}"}
    
    async def handle_list_jobs(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle list-jobs request
        
        Args:
            params: Request parameters
            
        Returns:
            List of recent jobs
        """
        limit = params.get("limit", 10)
        
        # Collect jobs from all operators
        all_jobs = []
        for project_name, operator in self.operators.items():
            all_jobs.extend(operator.list_jobs(limit=limit))
        
        # Sort by creation time (newest first) and limit
        sorted_jobs = sorted(
            all_jobs,
            key=lambda job: job.get("created_at", ""),
            reverse=True
        )[:limit]
        
        return sorted_jobs
    
    async def handle_add_note(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle add-note request
        
        Args:
            params: Request parameters
            
        Returns:
            Response data
        """
        name = params.get("name", "")
        content = params.get("content", "")
        
        if not name:
            logger.error("Missing name parameter")
            raise ValueError("Missing name parameter")
        
        if not content:
            logger.error("Missing content parameter")
            raise ValueError("Missing content parameter")
        
        # Use the first available operator to add the note
        # This is a simplification - ideally we should store notes independently
        if not self.operators:
            # Create a default operator if none exists
            default_project = "default-project"
            self.operators[default_project] = BrowserOperator(default_project)
        
        project_name = next(iter(self.operators.keys()))
        operator = self.operators[project_name]
        return await operator.add_note(name, content)
    
    # Browser tools handlers
    
    async def _get_active_operator(self) -> Tuple[str, BrowserOperator]:
        """Get an active operator, or create one if none exists
        
        Returns:
            Tuple of (project_name, operator)
        """
        if not self.operators:
            # Create a default operator if none exists
            default_project = "default-project"
            self.operators[default_project] = BrowserOperator(default_project)
            return default_project, self.operators[default_project]
        
        # Return the first operator that has an initialized browser
        for project_name, operator in self.operators.items():
            if operator.browser_instance and operator.browser_instance.initialized:
                return project_name, operator
        
        # If no initialized browsers, return the first operator
        project_name = next(iter(self.operators.keys()))
        return project_name, self.operators[project_name]
    
    async def handle_get_console_logs(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle getConsoleLogs request
        
        Args:
            params: Request parameters
            
        Returns:
            List of console log entries
        """
        _, operator = await self._get_active_operator()
        return await operator.get_console_logs()
    
    async def handle_get_console_errors(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle getConsoleErrors request
        
        Args:
            params: Request parameters
            
        Returns:
            List of console error entries
        """
        _, operator = await self._get_active_operator()
        return await operator.get_console_errors()
    
    async def handle_get_network_errors(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle getNetworkErrors request
        
        Args:
            params: Request parameters
            
        Returns:
            List of network error entries
        """
        _, operator = await self._get_active_operator()
        return await operator.get_network_errors()
    
    async def handle_get_network_logs(self, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Handle getNetworkLogs request
        
        Args:
            params: Request parameters
            
        Returns:
            List of network log entries
        """
        _, operator = await self._get_active_operator()
        return await operator.get_network_logs()
    
    async def handle_take_screenshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle takeScreenshot request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with screenshot data
        """
        _, operator = await self._get_active_operator()
        return await operator.take_screenshot()
    
    async def handle_get_selected_element(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle getSelectedElement request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with element information
        """
        _, operator = await self._get_active_operator()
        return await operator.get_selected_element()
    
    async def handle_wipe_logs(self, params: Dict[str, Any]) -> Dict[str, str]:
        """Handle wipeLogs request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with status message
        """
        _, operator = await self._get_active_operator()
        return await operator.wipe_logs()
    
    # Audit tools handlers
    
    async def handle_run_accessibility_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle runAccessibilityAudit request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with accessibility audit results
        """
        _, operator = await self._get_active_operator()
        return await operator.run_accessibility_audit()
    
    async def handle_run_performance_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle runPerformanceAudit request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with performance audit results
        """
        _, operator = await self._get_active_operator()
        return await operator.run_performance_audit()
    
    async def handle_run_seo_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle runSEOAudit request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with SEO audit results
        """
        _, operator = await self._get_active_operator()
        return await operator.run_seo_audit()
    
    async def handle_run_nextjs_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle runNextJSAudit request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with NextJS audit results
        """
        _, operator = await self._get_active_operator()
        return await operator.run_nextjs_audit()
    
    async def handle_run_best_practices_audit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle runBestPracticesAudit request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with best practices audit results
        """
        _, operator = await self._get_active_operator()
        return await operator.run_best_practices_audit()
    
    async def handle_run_debugger_mode(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle runDebuggerMode request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with debug information
        """
        _, operator = await self._get_active_operator()
        return await operator.run_debugger_mode()
    
    async def handle_run_audit_mode(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle runAuditMode request
        
        Args:
            params: Request parameters
            
        Returns:
            Dict with comprehensive audit results
        """
        _, operator = await self._get_active_operator()
        return await operator.run_audit_mode()
    
    # Main server loop
    
    async def listen(self):
        """Listen for incoming MCP requests from stdin"""
        logger.info("Starting MCP server")
        while True:
            try:
                # Read a line from stdin
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                
                if not line:
                    # EOF received, exit
                    logger.info("Received EOF, shutting down")
                    break
                
                # Parse JSON request
                try:
                    request_data = json.loads(line)
                    logger.debug(f"Received request: {request_data}")
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON request: {e}")
                    response = self._generate_error_response(
                        "",  # No ID available for invalid JSON
                        f"Invalid JSON request: {str(e)}",
                        -32700  # Parse error code
                    )
                else:
                    # Process the request
                    response = await self.handle_request(request_data)
                
                # Send the response
                response_json = json.dumps(response)
                logger.debug(f"Sending response: {response_json}")
                print(response_json, flush=True)
                
            except Exception as e:
                logger.exception("Unexpected error in server loop")
                # Try to send an error response
                error_response = self._generate_error_response(
                    "",  # No ID available for unexpected errors
                    f"Unexpected server error: {str(e)}"
                )
                try:
                    print(json.dumps(error_response), flush=True)
                except Exception:
                    # If we can't even send the error response, just log it
                    logger.critical("Failed to send error response")
    
    async def cleanup(self):
        """Close all browser instances and cleanup resources"""
        logger.info("Cleaning up before shutdown")
        
        # Close all browser operators
        for project_name, operator in self.operators.items():
            try:
                logger.info(f"Closing browser for project: {project_name}")
                await operator.close()
            except Exception as e:
                logger.error(f"Error closing browser for project {project_name}: {e}")
        
        # Clear the operators dictionary
        self.operators.clear()
        logger.info("Cleanup complete")

async def main():
    """Main entry point for the MCP server"""
    # Create the server
    server = MCPServer()
    
    # Set up signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()
    
    def signal_handler():
        logger.info("Received shutdown signal")
        # Schedule the cleanup
        asyncio.create_task(shutdown())
    
    async def shutdown():
        logger.info("Shutting down MCP server")
        await server.cleanup()
        loop.stop()
    
    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)
    
    try:
        # Start the server
        await server.listen()
    except Exception as e:
        logger.exception(f"Error in MCP server: {e}")
    finally:
        # Ensure cleanup on exit
        await server.cleanup()

if __name__ == "__main__":
    asyncio.run(main())