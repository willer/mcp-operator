#!/usr/bin/env python3
"""
Integration tests for the browser operator that use a real Playwright browser.
These tests verify that the actual browser interaction works correctly.
"""

import asyncio
import unittest
import os
import json
import argparse
from typing import Dict, Any

# Import the modules to test
from mcp_operator.browser import BrowserInstance, BrowserOperator

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run browser integration tests')
parser.add_argument('--headless', action='store_true', 
                    help='Run tests in headless mode (default: False)')
args = parser.parse_known_args()[0]

# Global variable to control headless mode
HEADLESS_MODE = args.headless

class IntegrationTestBrowserOperator(unittest.TestCase):
    """Integration tests for the browser operator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.browser_id = "integration-test-browser"
        self.temp_file = "/tmp/browser_operator_integration_test_result.json"
        
        # Clear any existing result file
        if os.path.exists(self.temp_file):
            os.unlink(self.temp_file)
            
    async def _setup_browser_operator(self):
        """Set up a browser operator with a real browser."""
        # Create browser operator
        operator = BrowserOperator(self.browser_id)
        
        # Override the headless setting in browser.py
        def modified_initialize(self):
            """Modified initialize method to control headless mode."""
            width, height = self.dimensions
            self.playwright = await self.playwright_context.__aenter__()
            
            # Override headless setting
            browser_options = {
                "headless": HEADLESS_MODE,
                "args": [
                    f"--window-size={width},{height+50}",
                    "--disable-extensions",
                    "--disable-infobars",
                    "--disable-notifications",
                    "--disable-background-timer-throttling",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-breakpad",
                    "--disable-component-extensions-with-background-pages",
                    "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                    "--disable-ipc-flooding-protection",
                    "--enable-automation",
                    "--start-maximized",
                    "--disable-popup-blocking",
                    "--noerrdialogs",
                    "--disable-prompt-on-repost"
                ]
            }
            
            if not HEADLESS_MODE:
                # Only add no-sandbox in non-headless mode
                browser_options["args"].append("--no-sandbox")
            
            self.browser = await self.playwright.chromium.launch(**browser_options)
            self.context = await self.browser.new_context()
            
            # Set up event listener for URL blocking
            async def handle_route(route, request):
                url = request.url
                if self.check_blocklisted_url(url):
                    print(f"Blocking access to: {url}")
                    await route.abort()
                else:
                    await route.continue_()
                    
            await self.context.route("**/*", handle_route)
            
            # Create new page
            self.page = await self.context.new_page()
            await self.page.set_viewport_size({"width": width, "height": height})
            
            # Set default timeout for all Playwright operations
            self.page.set_default_timeout(30000)
            
            # Go to Google as starting point
            await self.page.goto("https://google.com", wait_until='domcontentloaded')
            
            # Wait for network idle on Google homepage
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
            except:
                print("Google homepage partially loaded (network not idle)")
                
        # Monkey patch the initialize method
        BrowserInstance.original_initialize = BrowserInstance.initialize
        BrowserInstance.initialize = modified_initialize
        BrowserInstance.check_blocklisted_url = lambda self, url: False
        
        # Initialize browser with our patched method
        await operator.initialize()
        
        return operator
    
    def tearDown(self):
        """Tear down test fixtures."""
        # Restore original initialize method
        if hasattr(BrowserInstance, 'original_initialize'):
            BrowserInstance.initialize = BrowserInstance.original_initialize
            delattr(BrowserInstance, 'original_initialize')
        
        # Remove temp file if it exists
        if os.path.exists(self.temp_file):
            os.unlink(self.temp_file)
    
    async def test_navigate_to_url(self):
        """Test navigating to a URL with a real browser."""
        print("\nTesting real browser navigation to a URL...")
        operator = await self._setup_browser_operator()
        
        try:
            # Navigate to example.com
            result = await operator.navigate("https://example.com")
            
            # Verify the navigation was successful
            self.assertIn("Navigated to", result["text"])
            self.assertIsNotNone(result["screenshot"])
            
            # Take a screenshot and save it
            screenshot = await operator.browser_instance.take_screenshot()
            self.assertIsNotNone(screenshot)
            
            # Get the current URL
            current_url = await operator.browser_instance.get_current_url()
            self.assertEqual(current_url, "https://example.com/")
            
            print("✅ Navigation test passed")
        finally:
            # Close the browser
            await operator.close()
    
    async def test_click_interaction(self):
        """Test clicking on elements with a real browser."""
        print("\nTesting real browser click interaction...")
        operator = await self._setup_browser_operator()
        
        try:
            # Navigate to example.com (which has a link)
            await operator.navigate("https://example.com")
            
            # Get link position (we need to actually find it in the DOM)
            link_position = await operator.browser_instance.page.evaluate("""
                () => {
                    const link = document.querySelector('a');
                    if (!link) return null;
                    
                    const rect = link.getBoundingClientRect();
                    return {
                        x: Math.floor(rect.left + rect.width / 2),
                        y: Math.floor(rect.top + rect.height / 2)
                    };
                }
            """)
            
            self.assertIsNotNone(link_position, "Failed to find link on example.com")
            
            # Execute a click action on the link
            action = {
                "type": "click", 
                "x": link_position["x"], 
                "y": link_position["y"], 
                "button": "left"
            }
            result = await operator.execute_computer_action(action)
            
            # Verify the click was registered
            self.assertIn("Clicked at", result)
            
            # Wait for navigation to complete
            await asyncio.sleep(2)
            
            # Check if we navigated to the IANA site (linked from example.com)
            current_url = await operator.browser_instance.get_current_url()
            self.assertIn("iana.org", current_url)
            
            print("✅ Click interaction test passed")
        finally:
            # Close the browser
            await operator.close()
    
    async def test_multi_step_actions(self):
        """Test a sequence of actions with a real browser."""
        print("\nTesting multi-step actions with a real browser...")
        operator = await self._setup_browser_operator()
        
        try:
            # Create a sequence of actions to perform:
            # 1. Navigate to example.com
            # 2. Click on the "More information" link
            # 3. Wait for page to load
            # 4. Check if we're on the IANA site
            
            # Step 1: Navigate to example.com
            result = await operator.navigate("https://example.com")
            self.assertIn("Navigated to", result["text"])
            
            # Step 2: Find and click the link
            link_position = await operator.browser_instance.page.evaluate("""
                () => {
                    const link = document.querySelector('a');
                    if (!link) return null;
                    
                    const rect = link.getBoundingClientRect();
                    return {
                        x: Math.floor(rect.left + rect.width / 2),
                        y: Math.floor(rect.top + rect.height / 2)
                    };
                }
            """)
            
            self.assertIsNotNone(link_position, "Failed to find link on example.com")
            
            # Create API-like response items that would come from CUA
            response_items = [
                {
                    "type": "message",
                    "content": [{"type": "text", "text": "I'll navigate through the site."}]
                },
                {
                    "type": "computer_call",
                    "action": {
                        "type": "click", 
                        "x": link_position["x"], 
                        "y": link_position["y"], 
                        "button": "left"
                    }
                }
            ]
            
            # Process the response items as if they came from the CUA
            result = await operator.process_response_items(response_items)
            
            # Check the results
            self.assertIn("actions_executed", result)
            self.assertEqual(result["actions_executed"], 1)
            
            # Verify navigation occurred
            await asyncio.sleep(2)  # Wait for navigation
            current_url = await operator.browser_instance.get_current_url()
            self.assertIn("iana.org", current_url)
            
            print("✅ Multi-step actions test passed")
        finally:
            # Close the browser
            await operator.close()

async def run_tests():
    """Run all integration tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(IntegrationTestBrowserOperator)
    
    # Initialize results
    success = True
    
    # Display mode
    mode_str = "HEADLESS" if HEADLESS_MODE else "VISIBLE"
    print(f"\nRunning browser integration tests in {mode_str} mode...")
    print("=" * 60)
    
    # Run tests one by one to handle async
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
    
    print("\n" + "=" * 60)
    if success:
        print("All integration tests PASSED! ✨")
        return 0
    else:
        print("Some integration tests FAILED. 😢")
        return 1

if __name__ == "__main__":
    print(f"Running in {'headless' if HEADLESS_MODE else 'visible'} mode")
    asyncio.run(run_tests())