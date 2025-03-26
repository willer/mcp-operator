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
from pathlib import Path
from typing import Dict, Any, Optional

# Ensure the src directory is in the path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

# Import the modules to test
from mcp_operator.browser import BrowserOperator

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run real multi-step browser tests')
parser.add_argument('--headless', action='store_true', help='Run tests in headless mode (default: False)')
parser.add_argument('--task', type=str, default="news", 
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
        
        # Set up minimal route handler that only blocks obviously malicious domains
        async def handle_route(route, request):
            url = request.url
            
            # Very short list of obviously malicious domains to block
            blocklisted_domains = [
                'evil.com', 'malware.com', 'phishing.com', 'virus.com'
            ]
            
            # Only block obviously malicious domains
            if any(bad_domain in url.lower() for bad_domain in blocklisted_domains):
                logger.warning(f"Blocking access to harmful site: {url}")
                await route.abort()
            else:
                # Allow all other domains by default
                await route.continue_()
                
        await self.context.route("**/*", handle_route)
        
        # Create new page
        self.page = await self.context.new_page()
        await self.page.set_viewport_size({"width": width, "height": height})
        
        # Set default timeout for all Playwright operations
        self.page.set_default_timeout(30000)  # 30 seconds for all operations
        
        # Start with an empty page - let the agent figure out navigation
        logger.info("Starting with a blank page")
        try:
            # Start with about:blank - the agent should handle the navigation based on task
            await self.page.goto("about:blank", wait_until='domcontentloaded', timeout=10000)
            logger.info("Blank page loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load blank page: {str(e)}")
            # Nothing to fall back to if even about:blank fails
    
    # Apply the patched initialization method - completely replace the original method
    operator.browser_instance.initialize = patched_init.__get__(operator.browser_instance)
    
    # Initialize browser with our patched method
    print("🔄 Initializing browser...")
    
    # Apply the patch correctly
    try:
        await operator.browser_instance.initialize()
        
        # Directly create the agent without creating an additional AsyncLocalPlaywrightComputer
        # This prevents duplicate browser instances
        from mcp_operator.cua.agent import Agent
        operator.agent = Agent(
            model="gpt-4o-mini",  # Updated to latest model
            computer=None,  # Will be set below
            allowed_domains=['google.com', 'www.google.com', 'example.com', 'wikipedia.org', 'cnn.com', 'github.com', 'chromium.org', 'about:blank']  # Allow specific domains
        )
        
        # Import required modules for the adapter
        import base64
        import io
        
        # Create the computer directly from the browser we already have open
        class PlaywrightAdapter:
            """Adapter to make our Playwright browser work with the CUA Agent"""
            environment = "browser"
            dimensions = operator.browser_instance.dimensions
            
            def __init__(self, page):
                self._page = page
                self._browser = operator.browser_instance.browser
                # Store reference to required modules
                self.base64 = base64
                self.io = io
            
            # Implement the async context manager protocol
            async def __aenter__(self):
                """Async context manager entry - just return self since browser is already initialized"""
                return self
                
            async def __aexit__(self, exc_type, exc_value, traceback):
                """Async context manager exit - nothing to do, browser is managed elsewhere"""
                pass
            
            async def screenshot(self):
                """Take screenshot of current page"""
                png_bytes = await operator.browser_instance.page.screenshot(full_page=False)
                return self.base64.b64encode(png_bytes).decode("utf-8")
                
            async def click(self, x, y, button="left"):
                """Click at coordinates"""
                await operator.browser_instance.page.mouse.click(x, y, button=button)
                
            async def type(self, text):
                """Type text"""
                await operator.browser_instance.page.keyboard.type(text)
                
            async def keypress(self, keys):
                """Press keys"""
                for key in keys:
                    await operator.browser_instance.page.keyboard.press(key)
                    
            async def wait(self, ms=1000):
                """Wait for specified time"""
                await asyncio.sleep(ms / 1000)
                
            async def scroll(self, x, y, scroll_x, scroll_y):
                """Scroll page"""
                await operator.browser_instance.page.mouse.move(x, y)
                await operator.browser_instance.page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")
                
            async def move(self, x, y):
                """Move mouse"""
                await operator.browser_instance.page.mouse.move(x, y)
                
            async def drag(self, path):
                """Drag along path"""
                if not path:
                    return
                await operator.browser_instance.page.mouse.move(path[0]["x"], path[0]["y"])
                await operator.browser_instance.page.mouse.down()
                for point in path[1:]:
                    await operator.browser_instance.page.mouse.move(point["x"], point["y"])
                await operator.browser_instance.page.mouse.up()
                
            async def double_click(self, x, y):
                """Double-click at coordinates"""
                await operator.browser_instance.page.mouse.dblclick(x, y)
                
            async def get_current_url(self):
                """Get current page URL"""
                return operator.browser_instance.page.url
                
            async def goto(self, url):
                """Navigate to URL"""
                try:
                    await operator.browser_instance.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    print(f"Error navigating to {url}: {e}")
        
        # Create the adapter and set it on the agent
        adapter = PlaywrightAdapter(operator.browser_instance.page)
        operator.agent.computer = adapter
        
        print("✅ Browser and agent initialized correctly using direct adapter")
    except Exception as e:
        import traceback
        print(f"❌ Error initializing browser: {str(e)}")
        traceback.print_exc()
    
    try:
        # Choose the task based on command line argument
        instruction = ""
        if TASK_TYPE == "shopping":
            instruction = "Go to amazon.com, search for 'ceramic dish set', find a nice dish set under $50, and add it to the cart. Walk through all the steps one by one."
        elif TASK_TYPE == "search":
            instruction = "Go to google.com, search for 'Python programming tutorial', and click on one of the non-ad results."
        elif TASK_TYPE == "navigation":
            instruction = "Go to wikipedia.org, search for 'Artificial Intelligence', click on the main article, then find and click on a link to 'Machine Learning'."
        elif TASK_TYPE == "news":
            instruction = "Go to CNN's website, locate the top news article of the day, click on it, read it, and summarize it."
        else:
            instruction = f"Go to example.com and click on the 'More information' link. Then explore the page you land on."
        
        # Process the message, which should trigger a multi-step flow
        print(f"🚀 Starting multi-step task: {instruction}")
        print("-" * 80)
        
        # Directly call process_message which simulates what the operate-browser endpoint does
        start_time = time.time()
        try:
            result = await operator.process_message(instruction)
            elapsed_time = time.time() - start_time
        except Exception as e:
            print(f"❌ Error processing message: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
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
