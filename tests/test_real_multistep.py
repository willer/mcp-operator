#!/usr/bin/env python3
"""
End-to-end test for multi-step browser operations using a real browser.
This directly tests the operate-browser functionality with complex multi-step tasks.
"""

import os
import time
import sys
import unittest
import asyncio
from pathlib import Path

# Ensure the src directory is in the path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

# Import the modules to test
from mcp_operator.browser import BrowserOperator, BrowserInstance

# Default test settings with environment variable override
import os
HEADLESS_MODE = os.environ.get("TEST_HEADLESS", "true").lower() != "false"
EXAMPLE_URL = "https://example.com"

class TestRealMultistep(unittest.TestCase):
    """Test real multi-step browser operations"""
    
    def setUp(self):
        """Set up the test environment"""
        # Create a unique project name
        self.project_name = f"test-{int(time.time())}"
        
        # Create directories needed for the test
        for directory in ["logs", "screenshots", "notes"]:
            os.makedirs(os.path.join(Path(__file__).parent.parent, directory), exist_ok=True)
        
        # Initialize the event loop for async tests
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
    def tearDown(self):
        """Clean up after the test"""
        self.loop.close()
    
    def test_real_multistep(self):
        """Test a real multi-step browser operation using process_message"""
        # Run the async test in the loop
        mode_str = "HEADLESS" if HEADLESS_MODE else "VISIBLE"
        print(f"\n🔍 Running browser test in {mode_str} mode - {'browser will be invisible' if HEADLESS_MODE else 'watch your screen!'}") 
        print(f"💡 Tip: Set TEST_HEADLESS=false to see the browser window")
        result = self.loop.run_until_complete(self._async_test_real_multistep())
        self.assertTrue(result, "Multi-step test should complete successfully")
    
    async def _async_test_real_multistep(self):
        """Async implementation of the test"""
        print(f"\n🌐 Creating browser '{self.project_name}' to test multi-step operations...")
        
        # Create and initialize the operator
        operator = BrowserOperator(self.project_name)
        
        try:
            # Create the browser
            result = await operator.create_browser()
            job_id = result.get("job_id")
            print(f"Browser created with job ID: {job_id}")
            
            # Make sure browser_instance has headless mode set correctly
            operator.browser_instance.headless = HEADLESS_MODE
            print(f"Browser headless mode set to: {HEADLESS_MODE}")
            
            # Define a simple task that works reliably
            instruction = "Go to example.com and tell me the title of the page and what links are available"
            print(f"🚀 Starting multi-step task: {instruction}")
            
            # Execute the instruction
            start_time = time.time()
            result = await operator.process_message(instruction)
            elapsed_time = time.time() - start_time
            
            # Display results
            print(f"⏱️  Task completed in {elapsed_time:.2f} seconds")
            print(f"📝 Actions executed: {result.get('actions_executed', 0)}")
            
            # Check for success
            actions_executed = result.get('actions_executed', 0)
            success = actions_executed > 0
            
            # Get some result text to verify
            result_text = result.get("text", "")
            # Print the text for debugging
            print(f"\nResult text: {result_text[:500]}...\n")
            
            # Look for evidence of page analysis
            if "Example Domain" in result_text and "More information" in result_text:
                print("✅ Found expected page title and link information in result")
                success = True
            else:
                print("❌ Did not find expected page information in result")
                
            # Clean up
            await operator.close()
            print("✅ Browser closed")
            
            return success
            
        except Exception as e:
            import traceback
            print(f"❌ Error in multi-step test: {str(e)}")
            traceback.print_exc()
            
            # Try to clean up even if there's an error
            try:
                if operator:
                    await operator.close()
            except:
                pass
                
            return False

if __name__ == "__main__":
    unittest.main()