#!/usr/bin/env python3
"""
Test script specifically for multi-step browser operations.
This script focuses on testing the main methods in isolation.
"""

import asyncio
import unittest
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Import the modules to test
from mcp_operator.browser import BrowserOperator

class TestMultiStepProcessing(unittest.TestCase):
    """Test suite for multi-step operations, focusing on the core methods."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.project_name = "test-multistep"
    
    async def test_process_response_items(self):
        """Test that process_response_items correctly processes multiple action items."""
        # Create the operator with a mock browser instance
        operator = BrowserOperator(self.project_name)
        operator.browser_instance = AsyncMock()
        operator.browser_instance.take_screenshot.return_value = "base64screenshot"
        operator.browser_instance.get_current_url = AsyncMock(return_value="https://example.com")
        
        # Mock execute_computer_action to track calls
        with patch.object(operator, 'execute_computer_action', new_callable=AsyncMock) as mock_execute:
            # Set up return values for the execute_computer_action calls
            mock_execute.side_effect = [
                "Navigated to: https://example.com",
                "Clicked at (100, 200)",
                "Typed: test query"
            ]
            
            # Create test items similar to what the API would return
            items = [
                {"type": "message", "content": [{"type": "text", "text": "I'll help you with this task"}]},
                {"type": "computer_call", "action": {"type": "goto", "url": "https://example.com"}},
                {"type": "computer_call", "action": {"type": "click", "x": 100, "y": 200}},
                {"type": "computer_call", "action": {"type": "type", "text": "test query"}}
            ]
            
            # Call process_response_items directly
            result = await operator.process_response_items(items)
            
            # Verify execute_computer_action was called 3 times (for each computer_call)
            self.assertEqual(mock_execute.call_count, 3)
            
            # Check that each action type was correctly passed to execute_computer_action
            action_types = [call.args[0].get('type') for call in mock_execute.call_args_list]
            self.assertEqual(action_types, ['goto', 'click', 'type'])
            
            # Verify the result contains the expected fields
            self.assertIn("text", result)
            self.assertIn("screenshot", result)
            self.assertIn("actions_executed", result)
            
            # Check that the action count is correct
            self.assertEqual(result["actions_executed"], 3)
            
            # Ensure the result text contains the message text
            self.assertIn("help you with this task", result["text"])
    
    async def test_execute_computer_action_click(self):
        """Test that execute_computer_action can execute a click action."""
        # Create the operator with a mock browser instance
        operator = BrowserOperator(self.project_name)
        operator.browser_instance = AsyncMock()
        operator.browser_instance.page.mouse = AsyncMock()
        
        # Set up additional mocks for the enhanced click implementation
        operator.browser_instance.page.url = "https://example.com"
        operator.browser_instance.page.evaluate.return_value = {
            "tag": "BUTTON",
            "id": "search-button",
            "className": "btn btn-primary",
            "text": "Search",
            "isButton": True
        }
        
        # Execute a click action
        action = {"type": "click", "x": 100, "y": 200, "button": "left"}
        result = await operator.execute_computer_action(action)
        
        # Verify the browser's mouse.click was called with correct coordinates
        operator.browser_instance.page.mouse.click.assert_called_once_with(100, 200, button="left")
        
        # Verify the result text contains key information
        self.assertIn("Clicked at (100, 200)", result)
        # Our enhanced implementation should also mention the button
        self.assertIn("button", result)
        
    async def test_execute_computer_action_goto(self):
        """Test that execute_computer_action can execute a goto action."""
        # Create the operator with a mock browser instance
        operator = BrowserOperator(self.project_name)
        operator.browser_instance = AsyncMock()
        
        # Set up proper mocking for the new goto implementation
        operator.browser_instance.page.url = "https://example.com"
        operator.browser_instance.page.evaluate.return_value = "complete"
        
        # Execute a goto action
        action = {"type": "goto", "url": "https://example.com"}
        result = await operator.execute_computer_action(action)
        
        # Verify the browser's page.goto was called with the correct URL
        operator.browser_instance.page.goto.assert_called_once()
        self.assertEqual(operator.browser_instance.page.goto.call_args[0][0], "https://example.com")
        
        # Verify the result contains key information patterns
        self.assertIn("Navigated to:", result)
        self.assertIn("readyState", result)

async def run_tests():
    """Run the multi-step operation tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestMultiStepProcessing)
    
    # Initialize results
    success = True
    
    # Run tests one by one to handle async
    print("\nRunning multi-step processing tests...\n")
    
    for test in suite:
        test_method = getattr(test, test._testMethodName)
        test.setUp()
        try:
            if asyncio.iscoroutinefunction(test_method):
                await test_method()
                print(f"✅ {test._testMethodName}")
            else:
                test_method()
                print(f"✅ {test._testMethodName}")
        except Exception as e:
            print(f"❌ {test._testMethodName}: {e}")
            import traceback
            traceback.print_exc()
            success = False
        finally:
            if hasattr(test, 'tearDown'):
                test.tearDown()
    
    print("\n" + "=" * 50)
    if success:
        print("All tests PASSED! ✨")
        return 0
    else:
        print("Some tests FAILED. 😢")
        return 1

if __name__ == "__main__":
    print("Multi-step Processing Tests")
    print("=" * 50)
    asyncio.run(run_tests())