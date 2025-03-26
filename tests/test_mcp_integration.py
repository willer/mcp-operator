#!/usr/bin/env python3
"""
Integration tests for MCP Browser Operator
Tests the full MCP server by launching it as a subprocess and interacting with it
"""

import os
import sys
import json
import time
import base64
import asyncio
import unittest
import subprocess
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

class MCPClient:
    """A simple MCP client for testing"""
    
    def __init__(self, server_process):
        """Initialize with a server process"""
        self.server_process = server_process
        self.request_id = 0
    
    async def send_request(self, method, params=None):
        """Send a JSON-RPC request to the server"""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
        }
        
        if params is not None:
            request["params"] = params
        
        # Send the request
        request_json = json.dumps(request)
        self.server_process.stdin.write(request_json + "\n")
        self.server_process.stdin.flush()
        
        # Read the response
        try:
            response_line = self.server_process.stdout.readline().strip()
            if not response_line:
                return {"error": {"message": "No response received"}}
            
            response = json.loads(response_line)
            return response
        except json.JSONDecodeError:
            return {"error": {"message": f"Invalid JSON response: {response_line}"}}
    
    async def wait_for_job_completion(self, job_id, timeout=30):
        """Wait for a job to complete"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check job status
            response = await self.send_request(
                "mcp__browser-operator__get-job-status",
                {"job_id": job_id}
            )
            
            if "error" in response:
                return response
            
            if "result" in response and "status" in response["result"]:
                status = response["result"]["status"]
                if status == "completed":
                    return response
                elif status == "failed":
                    return response
            
            # Wait before retrying
            await asyncio.sleep(1)
        
        return {"error": {"message": f"Job did not complete within {timeout} seconds"}}

class TestMCPIntegration(unittest.TestCase):
    """Integration tests for MCP server"""

    @classmethod
    def setUpClass(cls):
        """Set up the MCP server process once for all tests"""
        # Create test directories if they don't exist
        for directory in ["logs", "screenshots", "notes"]:
            os.makedirs(os.path.join(project_root, directory), exist_ok=True)
        
        # Set log directory specifically for tests
        log_dir = os.path.join(project_root, "logs", "test")
        os.makedirs(log_dir, exist_ok=True)
        
        # Launch the MCP server process
        cls.server_process = subprocess.Popen(
            [os.path.join(project_root, "run-server"), "--log-dir", log_dir],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line-buffered
        )
        
        # Give the server a moment to start
        time.sleep(1)
        
        # Setup the event loop for async tests
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        
        # Create MCP client
        cls.client = MCPClient(cls.server_process)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up the MCP server process"""
        if cls.server_process:
            cls.server_process.terminate()
            try:
                cls.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server_process.kill()
                
            # Get stderr output for debugging
            stderr = cls.server_process.stderr.read()
            if stderr:
                print(f"\nServer stderr output:\n{stderr}")
        
        # Close the event loop
        cls.loop.close()
    
    def test_01_create_browser(self):
        """Test creating a browser instance"""
        async def run_test():
            # Create browser
            response = await self.client.send_request(
                "mcp__browser-operator__create-browser",
                {"project_name": "integration-test"}
            )
            
            # Check response
            self.assertIn("result", response, f"Error in response: {response}")
            self.assertIn("job_id", response["result"])
            
            # Wait for job completion
            job_id = response["result"]["job_id"]
            completion = await self.client.wait_for_job_completion(job_id)
            
            # Check job completion
            self.assertIn("result", completion)
            self.assertEqual(completion["result"]["status"], "completed")
            
            return job_id
        
        job_id = self.loop.run_until_complete(run_test())
        print(f"Browser created with job ID: {job_id}")
    
    def test_02_navigate_browser(self):
        """Test navigating the browser"""
        async def run_test():
            # Navigate to example.com
            response = await self.client.send_request(
                "mcp__browser-operator__navigate-browser",
                {
                    "project_name": "integration-test",
                    "url": "https://example.com"
                }
            )
            
            # Check response
            self.assertIn("result", response)
            self.assertIn("job_id", response["result"])
            
            # Wait for job completion
            job_id = response["result"]["job_id"]
            completion = await self.client.wait_for_job_completion(job_id)
            
            # Check job completion
            self.assertIn("result", completion)
            self.assertEqual(completion["result"]["status"], "completed")
            
            # Check result contains screenshot and current URL
            self.assertIn("result", completion["result"])
            result = completion["result"]["result"]
            self.assertIn("screenshot", result)
            self.assertIn("current_url", result)
            
            # URL should be example.com
            self.assertEqual(result["current_url"], "https://example.com/")
            
            # Save screenshot for visual inspection
            screenshot_dir = os.path.join(project_root, "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, "test_navigation.png")
            
            with open(screenshot_path, "wb") as f:
                f.write(base64.b64decode(result["screenshot"]))
            
            print(f"Navigation screenshot saved to: {screenshot_path}")
            
            return job_id
        
        job_id = self.loop.run_until_complete(run_test())
        print(f"Navigation completed with job ID: {job_id}")
    
    def test_03_add_note(self):
        """Test adding a note"""
        async def run_test():
            # Add a note
            response = await self.client.send_request(
                "mcp__browser-operator__add-note",
                {
                    "name": "Test Note",
                    "content": "This is a test note from the integration test."
                }
            )
            
            # Check response
            self.assertIn("result", response)
            self.assertIn("job_id", response["result"])
            
            # Wait for job completion
            job_id = response["result"]["job_id"]
            completion = await self.client.wait_for_job_completion(job_id)
            
            # Check job completion
            self.assertIn("result", completion)
            self.assertEqual(completion["result"]["status"], "completed")
            
            # Check result contains note file path
            self.assertIn("result", completion["result"])
            result = completion["result"]["result"]
            self.assertIn("note_file", result)
            
            # Verify note file exists
            note_file = result["note_file"]
            self.assertTrue(os.path.exists(note_file), f"Note file not found: {note_file}")
            
            return job_id
        
        job_id = self.loop.run_until_complete(run_test())
        print(f"Note added with job ID: {job_id}")
    
    def test_04_take_screenshot(self):
        """Test taking a screenshot"""
        async def run_test():
            # Take a screenshot
            response = await self.client.send_request(
                "mcp__browser-tools__takeScreenshot",
                {}
            )
            
            # Check response
            self.assertIn("result", response)
            self.assertIn("screenshot", response["result"])
            
            # Save screenshot for visual inspection
            screenshot_dir = os.path.join(project_root, "screenshots")
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, "test_screenshot_tool.png")
            
            with open(screenshot_path, "wb") as f:
                f.write(base64.b64decode(response["result"]["screenshot"]))
            
            print(f"Screenshot saved to: {screenshot_path}")
        
        self.loop.run_until_complete(run_test())
    
    def test_05_close_browser(self):
        """Test closing the browser"""
        async def run_test():
            # Close browser
            response = await self.client.send_request(
                "mcp__browser-operator__close-browser",
                {"project_name": "integration-test"}
            )
            
            # Check response
            self.assertIn("result", response)
            self.assertIn("job_id", response["result"])
            
            # Wait for job completion
            job_id = response["result"]["job_id"]
            completion = await self.client.wait_for_job_completion(job_id)
            
            # Check job completion
            self.assertIn("result", completion)
            self.assertEqual(completion["result"]["status"], "completed")
            
            return job_id
        
        job_id = self.loop.run_until_complete(run_test())
        print(f"Browser closed with job ID: {job_id}")
    
    def test_06_list_jobs(self):
        """Test listing jobs"""
        async def run_test():
            # List jobs
            response = await self.client.send_request(
                "mcp__browser-operator__list-jobs",
                {"limit": 5}
            )
            
            # Check response
            self.assertIn("result", response)
            jobs = response["result"]
            
            # Should have at least the jobs we've created
            self.assertGreaterEqual(len(jobs), 3)
            
            # Print jobs for debugging
            for job in jobs:
                print(f"Job {job['job_id']}: {job['operation']} - {job['status']}")
        
        self.loop.run_until_complete(run_test())

if __name__ == "__main__":
    unittest.main()