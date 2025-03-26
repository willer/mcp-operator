#!/usr/bin/env python3
"""
Unit tests for MCP Browser Operator methods
Tests the API methods without requiring a full server instance
"""

import asyncio
import unittest
import os
import sys
from pathlib import Path
import json
from unittest.mock import patch, MagicMock, AsyncMock

# Ensure the src directory is in the path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from mcp_operator.browser import BrowserOperator, BrowserInstance
from mcp_operator.server import MCPServer

class TestBrowserOperatorMethods(unittest.TestCase):
    """Test suite for BrowserOperator methods"""
    
    def setUp(self):
        """Set up test environment before each test"""
        self.browser_operator = BrowserOperator("test-project")
        # Mock the browser instance to avoid actual browser initialization
        self.browser_operator.browser_instance = MagicMock()
        self.browser_operator.browser_instance.initialized = True
        self.browser_operator.browser_instance.page = MagicMock()
        # Mock screenshot method to return a dummy base64 image
        dummy_screenshot = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        self.browser_operator.browser_instance.page.screenshot.return_value = dummy_screenshot.encode()
    
    def test_generate_job_id(self):
        """Test job ID generation"""
        job_id = self.browser_operator._generate_job_id()
        self.assertTrue(job_id.startswith("job-"))
        self.assertEqual(len(job_id), 4 + 32)  # "job-" prefix + 32 hex chars
    
    def test_list_jobs(self):
        """Test listing jobs"""
        # Create some test jobs
        job1 = MagicMock()
        job1.to_dict.return_value = {"job_id": "job-1", "created_at": "2023-01-01"}
        job1.created_at = "2023-01-01"
        
        job2 = MagicMock()
        job2.to_dict.return_value = {"job_id": "job-2", "created_at": "2023-01-02"}
        job2.created_at = "2023-01-02"
        
        job3 = MagicMock()
        job3.to_dict.return_value = {"job_id": "job-3", "created_at": "2023-01-03"}
        job3.created_at = "2023-01-03"
        
        self.browser_operator.jobs = {
            "job-1": job1,
            "job-2": job2,
            "job-3": job3
        }
        
        # Test listing all jobs
        jobs = self.browser_operator.list_jobs()
        self.assertEqual(len(jobs), 3)
        
        # Test limiting jobs
        jobs = self.browser_operator.list_jobs(limit=2)
        self.assertEqual(len(jobs), 2)
    
    def test_get_job_status(self):
        """Test getting job status"""
        # Create a test job
        mock_job = MagicMock()
        mock_job.to_dict.return_value = {
            "job_id": "job-test",
            "status": "completed",
            "result": {"success": True}
        }
        self.browser_operator.jobs["job-test"] = mock_job
        
        # Test getting status
        status = self.browser_operator.get_job_status("job-test")
        self.assertEqual(status["job_id"], "job-test")
        self.assertEqual(status["status"], "completed")
        
        # Test non-existent job
        status = self.browser_operator.get_job_status("job-nonexistent")
        self.assertIn("error", status)

class TestBrowserOperatorAsync(unittest.TestCase):
    """Asynchronous test suite for BrowserOperator methods"""
    
    def setUp(self):
        """Set up async test environment"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create patches
        self.patchers = []
        
        # Patch playwright for AsyncLocalPlaywrightComputer
        playwright_patcher = patch("playwright.async_api.async_playwright")
        self.mock_playwright = playwright_patcher.start()
        self.patchers.append(playwright_patcher)
        
        # Mock the playwright setup
        mock_playwright_context = AsyncMock()
        mock_playwright = AsyncMock()
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        
        # Link them together
        self.mock_playwright.return_value = mock_playwright_context
        mock_playwright_context.__aenter__.return_value = mock_playwright
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # Set up page mocks
        mock_page.screenshot.return_value = b"dummy_screenshot_data"
        mock_page.evaluate.return_value = {}
        
        # Create browser operator
        self.browser_operator = BrowserOperator("test-project")
    
    def tearDown(self):
        """Clean up after tests"""
        for patcher in self.patchers:
            patcher.stop()
        self.loop.close()
    
    def test_create_browser(self):
        """Test creating a browser"""
        async def _test():
            result = await self.browser_operator.create_browser()
            self.assertIn("job_id", result)
            job_id = result["job_id"]
            
            # Check job is created
            self.assertIn(job_id, self.browser_operator.jobs)
            job = self.browser_operator.jobs[job_id]
            self.assertEqual(job.operation, "create")
            
            # Since we mocked the browser creation, job should be completed
            self.assertEqual(job.status, "completed")
            
        self.loop.run_until_complete(_test())
    
    def test_navigate_browser(self):
        """Test navigating the browser"""
        async def _test():
            # First create the browser to ensure it's initialized
            await self.browser_operator.create_browser()
            
            # Test navigation
            result = await self.browser_operator.navigate_browser("https://example.com")
            self.assertIn("job_id", result)
            job_id = result["job_id"]
            
            # Check job is created
            self.assertIn(job_id, self.browser_operator.jobs)
            job = self.browser_operator.jobs[job_id]
            self.assertEqual(job.operation, "navigate")
            self.assertEqual(job.params["url"], "https://example.com")
            
            # Since we mocked navigation, job should be completed
            self.assertEqual(job.status, "completed")
            
        self.loop.run_until_complete(_test())
    
    def test_close_browser(self):
        """Test closing the browser"""
        async def _test():
            # First create the browser
            await self.browser_operator.create_browser()
            
            # Test closing
            result = await self.browser_operator.close()
            self.assertIn("job_id", result)
            job_id = result["job_id"]
            
            # Check job is created
            self.assertIn(job_id, self.browser_operator.jobs)
            job = self.browser_operator.jobs[job_id]
            self.assertEqual(job.operation, "close")
            
            # Since we mocked closing, job should be completed
            self.assertEqual(job.status, "completed")
            
        self.loop.run_until_complete(_test())

class TestMCPServer(unittest.TestCase):
    """Test MCP Server method dispatch"""
    
    def setUp(self):
        """Set up test environment"""
        self.server = MCPServer()
        
        # Patch BrowserOperator methods to avoid actual browser interactions
        self.browser_operator_patcher = patch("mcp_operator.server.BrowserOperator", autospec=True)
        self.mock_browser_operator_class = self.browser_operator_patcher.start()
        
        # Set up the mock browser operator
        self.mock_browser_operator = MagicMock()
        self.mock_browser_operator_class.return_value = self.mock_browser_operator
        
        # Setup async mock methods
        self.mock_browser_operator.create_browser = AsyncMock(return_value={"job_id": "test-job"})
        self.mock_browser_operator.navigate_browser = AsyncMock(return_value={"job_id": "test-job"})
        self.mock_browser_operator.operate_browser = AsyncMock(return_value={"job_id": "test-job"})
        self.mock_browser_operator.close = AsyncMock(return_value={"job_id": "test-job"})
        self.mock_browser_operator.add_note = AsyncMock(return_value={"job_id": "test-job"})
        
        # Setup sync mock methods
        self.mock_browser_operator.get_job_status = MagicMock(return_value={"job_id": "test-job", "status": "completed"})
        self.mock_browser_operator.list_jobs = MagicMock(return_value=[{"job_id": "test-job", "status": "completed"}])
    
    def tearDown(self):
        """Clean up after tests"""
        self.browser_operator_patcher.stop()
    
    def test_get_operator(self):
        """Test getting or creating operators"""
        operator = self.server._get_operator("test-project")
        self.assertEqual(operator, self.mock_browser_operator)
        
        # Check that the operator is cached
        self.assertIn("test-project", self.server.operators)
        
        # Getting the same operator should return the cached one
        operator2 = self.server._get_operator("test-project")
        self.assertEqual(operator, operator2)
        
        # Only one operator should have been created
        self.mock_browser_operator_class.assert_called_once_with("test-project")
    
    def test_dispatch_method(self):
        """Test dispatching methods"""
        async def _test():
            # Test dispatching create-browser
            response = await self.server.dispatch_method(
                "mcp__browser-operator__create-browser",
                {"project_name": "test-project"},
                "req-1"
            )
            
            # Check response structure
            self.assertEqual(response["jsonrpc"], "2.0")
            self.assertEqual(response["id"], "req-1")
            self.assertEqual(response["result"], {"job_id": "test-job"})
            
            # Check that the method was called
            self.mock_browser_operator.create_browser.assert_called_once()
            
            # Test error response for unknown method
            response = await self.server.dispatch_method(
                "unknown_method",
                {},
                "req-2"
            )
            
            # Check error response
            self.assertEqual(response["jsonrpc"], "2.0")
            self.assertEqual(response["id"], "req-2")
            self.assertIn("error", response)
            self.assertEqual(response["error"]["code"], -32601)  # Method not found
            
        # Run the async test
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_test())
        finally:
            loop.close()

class TestBrowserToolsMethods(unittest.TestCase):
    """Test browser tools and audit methods"""
    
    def setUp(self):
        """Set up test environment"""
        self.browser_operator = BrowserOperator("test-project")
        
        # Mock the browser instance 
        self.browser_operator.browser_instance = MagicMock()
        self.browser_operator.browser_instance.initialized = True
        self.browser_operator.browser_instance.page = MagicMock()
        
        # Set up page mocks
        dummy_screenshot = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        self.browser_operator.browser_instance.page.screenshot.return_value = dummy_screenshot.encode()
        self.browser_operator.browser_instance.page.evaluate.return_value = {}
        self.browser_operator.browser_instance.page.url = "https://example.com"
    
    def test_audit_methods(self):
        """Test that all audit methods are properly defined"""
        # List of all audit methods
        audit_methods = [
            "_run_audit",
            "run_accessibility_audit", 
            "run_performance_audit",
            "run_seo_audit", 
            "run_nextjs_audit",
            "run_best_practices_audit", 
            "run_debugger_mode",
            "run_audit_mode"
        ]
        
        # Verify each method exists
        for method_name in audit_methods:
            self.assertTrue(hasattr(self.browser_operator, method_name))
            self.assertTrue(callable(getattr(self.browser_operator, method_name)))
    
    def test_browser_tool_methods(self):
        """Test that all browser tool methods are properly defined"""
        # List of all browser tool methods
        browser_tools = [
            "get_console_logs",
            "get_console_errors",
            "get_network_logs",
            "get_network_errors",
            "take_screenshot",
            "get_selected_element",
            "wipe_logs"
        ]
        
        # Verify each method exists
        for method_name in browser_tools:
            self.assertTrue(hasattr(self.browser_operator, method_name))
            self.assertTrue(callable(getattr(self.browser_operator, method_name)))

# Run the tests
if __name__ == "__main__":
    unittest.main()