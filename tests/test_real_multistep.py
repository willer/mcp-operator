#!/usr/bin/env python3
"""
End-to-end test for multi-step browser operations using a real browser.
This directly tests the operate-browser functionality with complex multi-step tasks.
"""

import asyncio
import os
import argparse
import time
import sys
import json
from typing import Dict, Any, Optional

# Import the modules to test
from mcp_operator.browser import BrowserOperator

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run real multi-step browser tests')
parser.add_argument('--headless', action='store_true', help='Run tests in headless mode (default: False)')
parser.add_argument('--task', type=str, default="shopping", 
                    help='Task to test (shopping, search, navigation)')
args = parser.parse_known_args()[0]

# Global variables to control test behavior
HEADLESS_MODE = args.headless
TASK_TYPE = args.task

async def test_real_multistep_operation():
    """
    Test a real multi-step browser operation that directly uses process_message.
    This mimics how operate-browser would be called via the MCP server.
    """
    # Create operator with unique name for this test
    browser_id = f"test-multistep-{int(time.time())}"
    print(f"\n🌐 Creating browser '{browser_id}' to test multi-step operations...")
    operator = BrowserOperator(browser_id)
    
    # Patch the browser initialization to control headless mode
    orig_init = operator.browser_instance.initialize
    
    async def patched_init(self):
        """Modified initialize method to control headless mode and browser options."""
        import logging
        logger = logging.getLogger('mcp-operator')
        width, height = self.dimensions
        
        from playwright.async_api import async_playwright
        self.playwright_context = async_playwright()
        self.playwright = await self.playwright_context.__aenter__()
        
        # Override browser launch options
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
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection",
                "--enable-automation",
                "--start-maximized",
                "--disable-popup-blocking",
                "--noerrdialogs",
                "--disable-prompt-on-repost",
                "--no-default-browser-check"
            ]
        }
        
        if not HEADLESS_MODE:
            browser_options["args"].append("--no-sandbox")  # This can help with focus issues
        
        logger.info(f"Launching browser with patched options: {browser_options}")
        self.browser = await self.playwright.chromium.launch(**browser_options)
        self.context = await self.browser.new_context()
        
        # Set up event listener for URL blocking
        async def handle_route(route, request):
            url = request.url
            from mcp_operator.browser import check_blocklisted_url
            if check_blocklisted_url(url):
                logger.warning(f"Blocking access to: {url}")
                await route.abort()
            else:
                await route.continue_()
                
        await self.context.route("**/*", handle_route)
        
        # Create new page
        self.page = await self.context.new_page()
        await self.page.set_viewport_size({"width": width, "height": height})
        
        # Set default timeout for all Playwright operations
        self.page.set_default_timeout(30000)  # 30 seconds for all operations
        
        # Always start with Google
        logger.info("Navigating to Google as starting point")
        try:
            await self.page.goto("https://google.com", wait_until='domcontentloaded', timeout=20000)
            
            # Wait for network idle to ensure Google is fully loaded
            try:
                await self.page.wait_for_load_state('networkidle', timeout=5000)
                logger.info("Google homepage fully loaded")
            except:
                logger.warning("Google homepage partially loaded (network not idle)")
                
        except Exception as e:
            logger.error(f"Failed to load Google: {str(e)}")
            try:
                # Try a simpler approach as fallback
                await self.page.goto("about:blank")
                logger.info("Loaded about:blank as fallback")
            except Exception as e2:
                logger.error(f"Failed to load fallback page: {str(e2)}")
    
    # Apply the patched initialization method
    operator.browser_instance.initialize = patched_init.__get__(operator.browser_instance)
    
    # Initialize browser with our patched method
    print("🔄 Initializing browser...")
    await operator.initialize()
    print("✅ Browser initialized")
    
    try:
        # Choose the task based on command line argument
        instruction = ""
        if TASK_TYPE == "shopping":
            instruction = "Go to amazon.com, search for 'ceramic dish set', find a nice dish set under $50, and add it to the cart. Walk through all the steps one by one."
        elif TASK_TYPE == "search":
            instruction = "Go to google.com, search for 'Python programming tutorial', and click on one of the non-ad results."
        elif TASK_TYPE == "navigation":
            instruction = "Go to wikipedia.org, search for 'Artificial Intelligence', click on the main article, then find and click on a link to 'Machine Learning'."
        else:
            instruction = f"Go to example.com and click on the 'More information' link. Then explore the page you land on."
        
        # Process the message, which should trigger a multi-step flow
        print(f"🚀 Starting multi-step task: {instruction}")
        print("-" * 80)
        
        # Directly call process_message which simulates what the operate-browser endpoint does
        start_time = time.time()
        result = await operator.process_message(instruction)
        elapsed_time = time.time() - start_time
        
        # Print the results
        print("-" * 80)
        print(f"⏱️  Task completed in {elapsed_time:.2f} seconds")
        print(f"📝 Actions executed: {result.get('actions_executed', 0)}")
        
        # Extract and print the result text, but limit its length
        result_text = result.get("text", "")
        if len(result_text) > 1000:
            result_text = result_text[:500] + "\n...[output truncated]...\n" + result_text[-500:]
        print(f"🔍 Result:\n{result_text}")
        
        # Save the screenshot for inspection if not in headless mode
        if not HEADLESS_MODE and "screenshot" in result:
            screenshot_path = f"/tmp/multistep_test_screenshot_{browser_id}.png"
            import base64
            with open(screenshot_path, "wb") as f:
                f.write(base64.b64decode(result["screenshot"]))
            print(f"📸 Screenshot saved to: {screenshot_path}")
        
        # Check if the task ran properly
        success = result.get("actions_executed", 0) > 1
        if success:
            print("✅ Multi-step test PASSED - multiple actions were executed")
            return True
        else:
            print("❌ Multi-step test FAILED - no or insufficient actions executed")
            return False
            
    except Exception as e:
        import traceback
        print(f"❌ Error in multi-step test: {str(e)}")
        traceback.print_exc()
        return False
    finally:
        # Close the browser
        print("🔄 Closing browser...")
        await operator.close()
        print("✅ Browser closed")

async def run_test():
    """Run the real multi-step browser test."""
    mode_str = "HEADLESS" if HEADLESS_MODE else "VISIBLE"
    task_str = TASK_TYPE.upper()
    
    print(f"\n===== REAL MULTI-STEP BROWSER TEST ({mode_str}, {task_str}) =====")
    
    # Run the test and get the result
    success = await test_real_multistep_operation()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 Real multi-step test PASSED! This means the multi-step flow is working.")
        return 0
    else:
        print("😢 Real multi-step test FAILED. The multi-step flow is not working properly.")
        return 1

if __name__ == "__main__":
    # Print mode and task information
    print(f"Running in {'headless' if HEADLESS_MODE else 'visible'} mode")
    print(f"Task: {TASK_TYPE}")
    
    # Run the test
    exit_code = asyncio.run(run_test())
    sys.exit(exit_code)