#!/usr/bin/env python3

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import tempfile
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse

import aiohttp
import dotenv
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

# Load environment variables
dotenv.load_dotenv()

# Set up logger for use throughout the module
logger = logging.getLogger('mcp-operator')

# Ensure no handlers that could output to stdout/stderr
for handler in logging.root.handlers[:]:
    if isinstance(handler, logging.StreamHandler):
        logging.root.removeHandler(handler)

# List of blocked domains for safety
BLOCKED_DOMAINS = [
    "maliciousbook.com",
    "evilvideos.com",
    "darkwebforum.com",
    "shadytok.com",
    "suspiciouspins.com",
]

def check_blocklisted_url(url: str) -> bool:
    """Check if the given URL (including subdomains) is in the blocklist."""
    hostname = urlparse(url).hostname or ""
    if any(hostname == blocked or hostname.endswith(f".{blocked}") for blocked in BLOCKED_DOMAINS):
        return True
    return False


class BrowserInstance:
    """A class to manage a browser instance using Playwright with persistent state support."""
    
    def __init__(self, project_name: str, dimensions: Tuple[int, int] = (1024, 768)):
        self.project_name = project_name
        self.dimensions = dimensions
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.current_conversation = []
        
        # Project-based persistence
        self.state_hash = self._hash_project_name(self.project_name)
        self.state_dir = os.path.join(tempfile.gettempdir(), "mcp_browser_states")
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, f"{self.state_hash}.json")
        
        import logging
        logger = logging.getLogger('mcp-operator')
        logger.info(f"Browser instance created for project: {project_name}")
        logger.info(f"State file: {self.state_file}")
    
    def _hash_project_name(self, project_name: str) -> str:
        """Create a hash of the project name for unique identification."""
        return hashlib.md5(project_name.encode()).hexdigest()
        
    async def save_state(self):
        """Save the browser state to a file."""
        # State saving is temporarily disabled while we debug the tab issue
        # TODO: Re-enable state saving after fixing the tab creation issue
        logger.debug("Browser state saving temporarily disabled")
        return
        
        # The code below is disabled for now
        if False and self.context:
            try:
                state = await self.context.storage_state()
                
                # Add additional state info
                state_info = {
                    "storage": state,
                    "last_url": self.page.url if self.page else "",
                    "project_name": self.project_name,
                    "timestamp": asyncio.get_event_loop().time(),
                }
                
                # Write to file
                with open(self.state_file, 'w') as f:
                    json.dump(state_info, f)
                    
                logger.debug(f"Browser state saved to {self.state_file}")
            except Exception as e:
                logger.error(f"Error saving browser state: {str(e)}")
            
    async def load_state(self):
        """Load the browser state from a file if it exists."""
        # State loading is temporarily disabled while we debug the tab issue
        # TODO: Re-enable state loading after fixing the tab creation issue
        logger.debug("Browser state loading temporarily disabled")
        return None
        
        # The code below is disabled for now
        if False and os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state_info = json.load(f)
                    
                logger.info(f"Loaded previous browser state from {self.state_file}")
                return state_info
            except Exception as e:
                logger.error(f"Error loading browser state: {str(e)}")
                return None
        
    async def initialize(self):
        """Initialize the browser instance, loading state if available."""
        width, height = self.dimensions
        self.playwright = await async_playwright().start()
        
        # Get logger reference
        import logging
        logger = logging.getLogger('mcp-operator')
        
        # Determine if we're in test mode
        is_test_mode = 'test' in os.environ.get('PYTHONPATH', '').lower()
        
        # State management is completely disabled for now
        state_info = None
        
        # Launch browser with improved flags for focus control and reliability
        browser_options = {
            "headless": False,  # Makes the browser visible
            "args": [
                f"--window-size={width},{height+50}",  # Add a bit more height for controls
                "--disable-extensions",
                "--disable-infobars",  # Disable Chrome's info bars which can interfere with automation
                "--disable-notifications",  # Disable notifications which might block interaction
                "--disable-background-timer-throttling",  # Improves reliability when tab is not in focus
                "--disable-backgrounding-occluded-windows",  # Keeps tabs active even when not focused
                "--disable-breakpad",  # Disable crash reporting
                "--disable-component-extensions-with-background-pages",  # Reduces resource usage
                "--disable-features=TranslateUI,BlinkGenPropertyTrees",  # Disable UI popups
                "--disable-ipc-flooding-protection",  # Improves performance for automation
                "--enable-automation",  # Explicitly enable automation mode
                "--start-maximized",  # Maximize window to avoid size issues
                "--disable-popup-blocking",  # Allow popups for better navigation handling
                "--noerrdialogs",  # Suppress error dialogs that might steal focus
                "--disable-prompt-on-repost"  # Don't show repost prompts
            ]
        }
        
        # Only add no-sandbox in regular mode, not test mode
        if not is_test_mode:
            browser_options["args"].append("--no-sandbox")  # This prevents focus stealing but can cause issues in some envs
        
        # Add channel option for stable release
        browser_options["channel"] = "chrome"
        
        # Launch the browser with all options
        logger.info(f"Launching browser with options: {browser_options}")
        self.browser = await self.playwright.chromium.launch(**browser_options)
        
        # Always create a fresh context - state loading is disabled
        logger.info("Creating new browser context (state management disabled)")
        self.context = await self.browser.new_context()
        
        # Set up event listener for URL blocking
        async def handle_route(route, request):
            url = request.url
            if check_blocklisted_url(url):
                logger.warning(f"Blocking access to: {url}")
                await route.abort()
            else:
                await route.continue_()
                
        await self.context.route("**/*", handle_route)
        
        # Create new page
        self.page = await self.context.new_page()
        await self.page.set_viewport_size({"width": width, "height": height})
        
        # Set default timeout for all Playwright operations to be more patient
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
        
        # Explicitly NOT saving state - state management is disabled
        
    async def take_screenshot(self) -> Optional[str]:
        """Take a screenshot of the current page."""
        import logging
        logger = logging.getLogger('mcp-operator')
        
        if not self.page:
            logger.warning("Cannot take screenshot: page not initialized")
            return None
        
        try:
            screenshot_bytes = await self.page.screenshot(full_page=False)
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as e:
            logger.error(f"Screenshot error: {str(e)}")
            return None
    
    async def get_current_url(self) -> str:
        """Get the current URL of the page."""
        if not self.page:
            return ""
        return self.page.url
    
    async def navigate(self, url: str):
        """Navigate to a URL and save state afterwards."""
        import logging
        logger = logging.getLogger('mcp-operator')
        
        if not self.page:
            logger.warning("Cannot navigate: page not initialized")
            return False
            
        try:
            await self.page.goto(url, wait_until='domcontentloaded')
            
            # Save state after successful navigation
            if hasattr(self, 'persistent') and self.persistent:
                await self.save_state()
                
            return True
        except Exception as e:
            logger.error(f"Navigation error: {str(e)}")
            return False
        
    async def close(self):
        """Save state and close the browser instance."""
        # Save final state before closing
        if self.context:
            await self.save_state()
            
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.context = None
            self.page = None
        
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None


class BrowserOperator:
    """A class to operate a browser using the OpenAI Computer Use API."""
    
    def __init__(self, project_name: str):
        import logging
        logger = logging.getLogger('mcp-operator')
        
        self.project_name = project_name
        self.browser_instance = BrowserInstance(project_name)
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY environment variable not set! Computer Use API will not work.")
        self.conversation = []
        self.last_reasoning = None  # Store reasoning for better action context
        self.print_steps = True     # Print steps for debugging (controls debug logging level)
        
    async def initialize(self):
        """Initialize the browser operator."""
        await self.browser_instance.initialize()
    
    def generate_action_reasoning(self, action_type, action_args):
        """Generate contextual reasoning for different action types"""
        action_reasoning = {
            "click": "Clicking on an element to interact with the page interface. This helps navigate through the content.",
            "double_click": "Double-clicking on an element to open or expand content that may contain relevant information.",
            "type": "Typing text to provide input needed for this task.",
            "keypress": "Pressing keys to interact with the page.",
            "scroll": "Scrolling the page to view additional content.",
            "goto": "Navigating to a website.",
            "wait": "Waiting for the page to respond or load content.",
            "move": "Moving the cursor to prepare for the next interaction.",
            "drag": "Adjusting the view or interacting with content by dragging.",
            "screenshot": "Capturing a screenshot to record the visual information displayed."
        }
        
        # Get default reasoning for this action type
        base_reasoning = action_reasoning.get(action_type, f"Performing {action_type} action.")
        
        # Add specific details based on action type and args
        if action_type == "click":
            x = action_args.get("x", 0)
            y = action_args.get("y", 0)
            return f"Clicking at position ({x}, {y}) - {base_reasoning}"
        elif action_type == "type":
            text = action_args.get("text", "")
            if len(text) > 30:
                text = text[:30] + "..."
            return f"Typing '{text}' - {base_reasoning}"
        elif action_type == "keypress":
            keys = action_args.get("keys", [])
            if isinstance(keys, list):
                keys = ", ".join(keys)
            return f"Pressing keys: {keys} - {base_reasoning}"
        elif action_type == "scroll":
            x = action_args.get("scroll_x", 0)
            y = action_args.get("scroll_y", 0)
            direction = "down" if y > 0 else "up"
            return f"Scrolling {direction} - {base_reasoning}"
        elif action_type == "wait":
            return f"Waiting - {base_reasoning}"
        
        # Return default reasoning with action type
        return base_reasoning
    
    async def navigate(self, url: str) -> dict:
        """Navigate to a URL directly."""
        if not self.browser_instance.page:
            return {"text": "Browser not initialized"}
        
        # Handle special case for yahoo.com which often causes timeouts
        if "yahoo.com" in url.lower():
            logger.info(f"Yahoo.com detected, using reduced wait state approach")
            
            try:
                # Set a shorter timeout for initial navigation
                navigate_future = asyncio.ensure_future(
                    self.browser_instance.page.goto(url, timeout=15000, wait_until='domcontentloaded')
                )
                
                try:
                    # Wait but don't block too long
                    await asyncio.wait_for(navigate_future, timeout=20)
                except asyncio.TimeoutError:
                    logger.info("Navigation timeout, but continuing...")
                    # Even with timeout, we can still get a screenshot
                
                # Take screenshot of whatever state we reached
                await asyncio.sleep(1)  # Brief pause to let rendering happen
                screenshot = await self.browser_instance.take_screenshot()
                return {
                    "text": f"Attempted navigation to {url} (Yahoo sites may load slowly)",
                    "screenshot": screenshot
                }
            except Exception as e:
                logger.error(f"Navigation error with yahoo: {str(e)}")
                try:
                    # Try to get what we can
                    screenshot = await self.browser_instance.take_screenshot()
                    return {
                        "text": f"Error navigating to {url}: {str(e)}",
                        "screenshot": screenshot
                    }
                except:
                    return {"text": f"Error navigating to Yahoo: {str(e)}"}
        
        # Standard navigation for non-yahoo urls
        try:
            # More aggressive timeouts with wait_until: domcontentloaded instead of load
            # This will return once the DOM is built but before all resources load
            logger.info(f"Navigating to {url}...")
            
            timeout_task = asyncio.create_task(
                self.browser_instance.page.goto(url, timeout=20000, wait_until='domcontentloaded')
            )
            
            # Wait for navigation with timeout
            try:
                await asyncio.wait_for(timeout_task, timeout=25)
                logger.info(f"Navigation to {url} completed")
            except asyncio.TimeoutError:
                logger.warning(f"Navigation to {url} timed out, but proceeding with partial load")
                # Cancel the task explicitly to avoid orphaned tasks
                timeout_task.cancel()
                try:
                    await timeout_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
            
            # Take screenshot of whatever state we reached
            await asyncio.sleep(1)  # Brief pause to let rendering happen
            screenshot = await self.browser_instance.take_screenshot()
            
            if await self.browser_instance.get_current_url() == url or url in await self.browser_instance.get_current_url():
                return {
                    "text": f"Navigated to {url}",
                    "screenshot": screenshot
                }
            else:
                return {
                    "text": f"Partial navigation to {url} (current: {await self.browser_instance.get_current_url()})",
                    "screenshot": screenshot
                }
        except Exception as e:
            logger.error(f"Navigation error: {str(e)}")
            # Try to get a screenshot even if navigation had an error
            try:
                screenshot = await self.browser_instance.take_screenshot()
                return {
                    "text": f"Error navigating to {url}: {str(e)}",
                    "screenshot": screenshot
                }
            except Exception as screenshot_err:
                logger.error(f"Error taking screenshot: {str(screenshot_err)}")
                return {"text": f"Error navigating to {url}: {str(e)}"}
    
    async def call_computer_use_api(self, user_message: str, screenshot: str, current_url: str) -> dict:
        """Call the OpenAI Computer Use API."""
        # Set up the tools array with computer-preview tool
        tools = [
            {
                "type": "computer-preview",
                "display_width": self.browser_instance.dimensions[0],
                "display_height": self.browser_instance.dimensions[1],
                "environment": "browser"
            }
        ]
        
        # The conversation has already been prepared in process_message with system 
        # and user messages, so we don't need to modify it here.
        # We'll just directly use the conversation in the API call.
        
        # Call the OpenAI Responses API (CUA endpoint)
        try:
            url = "https://api.openai.com/v1/responses"
            headers = {
                "Authorization": f"Bearer {self.openai_api_key}",
                "Content-Type": "application/json",
                "Openai-Beta": "responses=v1"  # Note: case matters for some servers
            }
            
            openai_org = os.environ.get("OPENAI_ORG")
            if openai_org:
                headers["OpenAI-Organization"] = openai_org
            
            # Prepare API payload
            payload = {
                "model": "computer-use-preview",
                "input": self.conversation,
                "tools": tools,
                "truncation": "auto",
                "temperature": 0.2  # Small amount of temperature to avoid deterministic errors
            }
            
            logger.info(f"Calling OpenAI CUA API with {len(self.conversation)} conversation items...")
            
            # API request with proper error handling
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"API Error: {error_text}")
                        return {"text": f"Error from OpenAI API: {error_text}"}
                    
                    # Get response and parse it
                    response_text = await response.text()
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse API response: {response_text[:200]}...")
                        return {"text": "Error: Invalid response format from API"}
            
            if "output" not in result:
                return {"text": "No output from OpenAI API"}
                
            # Check for reasoning in the response object
            if "reasoning" in result:
                reasoning_obj = result.get("reasoning", {})
                if isinstance(reasoning_obj, dict):
                    # Try to extract from various fields based on API structure
                    if "description" in reasoning_obj:
                        reasoning_text = reasoning_obj["description"]
                        if self.print_steps:
                            logger.debug(f"API Reasoning: {reasoning_text}")
                        self.last_reasoning = reasoning_text
                    elif "explanation" in reasoning_obj:
                        reasoning_text = reasoning_obj["explanation"]
                        if self.print_steps:
                            logger.debug(f"API Reasoning: {reasoning_text}")
                        self.last_reasoning = reasoning_text
            
            response_items = result["output"]
            logger.info(f"Received {len(response_items)} response items from CUA API")
            
            # Debug output to check what kinds of items we're getting
            response_types = [item.get("type") for item in response_items]
            logger.debug(f"Response item types: {response_types}")
            
            # Check if we have any computer_call actions
            has_computer_calls = any(item.get("type") == "computer_call" for item in response_items)
            if not has_computer_calls and len(response_items) > 0:
                logger.warning("No computer_call actions in the response, only messages")
            
            # Process each item in the response
            return await self.process_response_items(response_items)
            
        except Exception as e:
            logger.error(f"Error calling OpenAI API: {str(e)}")
            import traceback
            error_tb = traceback.format_exc()
            logger.error(error_tb)
            return {"text": f"Error calling OpenAI API: {str(e)}"}
    
    async def process_response_items(self, items):
        """Process the response items from the Computer Use API."""
        results = []
        final_text = ""
        commentary = []
        actions_executed = 0
        messages_received = 0
        max_iterations = 10  # Safety limit to prevent infinite loops
        iterations = 0
        continue_execution = True
        
        logger.info(f"Processing {len(items)} response items from CUA")
        
        # Check if items array is empty
        if not items:
            logger.warning("Empty response items from CUA API")
            return {
                "text": "The browser automation system didn't return any actions to execute. Please try again with more specific instructions.",
                "screenshot": await self.browser_instance.take_screenshot(),
                "actions_executed": 0
            }
        
        # Process all items in a loop until we've completed all necessary actions
        while continue_execution and iterations < max_iterations:
            iterations += 1
            logger.info(f"Execution iteration {iterations}")
            
            # Check for event synchronization issues
            if iterations == 1:
                # Verify browser events are working properly on first iteration
                logger.info("Verifying browser event handling")
            
            # Process current batch of items
            actions_in_this_iteration = 0
            for item in items:
                logger.info(f"Processing CUA response item type: {item.get('type')}")
                
                if item.get("type") == "message":
                    messages_received += 1
                    if "content" in item and len(item["content"]) > 0:
                        for content_item in item["content"]:
                            if content_item.get("type") == "text" or content_item.get("type") == "output_text":
                                message_text = content_item.get("text", "")
                                
                                # Extract reasoning from message if available
                                import re
                                reasoning_pattern = r'(I am|I\'m|I will|My plan is|My reasoning is|My thought process is|I think|Let me|I need to|First|Next|Now)(.*?)(?=I will now|Next I will|Now I will|I am going to|I\'m going to|\Z)'
                                reasoning_match = re.search(reasoning_pattern, message_text, re.DOTALL | re.IGNORECASE)
                                
                                if reasoning_match:
                                    reasoning_text = reasoning_match.group(0).strip()
                                    self.last_reasoning = reasoning_text
                                    logger.debug(f"Extracted reasoning: {reasoning_text[:100]}...")
                                    results.append(f"💡 Reasoning: {reasoning_text}")
                                
                                # Add the message text to results
                                final_text += message_text + "\n\n"
                                commentary.append(f"💬 {message_text[:100]}...")
                                logger.debug(f"CUA message: {message_text[:100]}...")
                                results.append(f"[AI] {message_text}")
                
                elif item.get("type") == "computer_call":
                    actions_executed += 1
                    actions_in_this_iteration += 1
                    action = item.get("action", {})
                    action_type = action.get("type")
                    
                    # Log what we're about to do
                    action_desc = f"🖱️ {action_type}"
                    if action_type == "click":
                        action_desc = f"🖱️ Clicking at ({action.get('x', 0)}, {action.get('y', 0)})"
                    elif action_type == "type":
                        action_desc = f"⌨️ Typing: {action.get('text', '')}"
                    elif action_type == "goto":
                        action_desc = f"🌐 Going to {action.get('url', '')}"
                    elif action_type == "scroll":
                        action_desc = f"📜 Scrolling ({action.get('scroll_x', 0)}, {action.get('scroll_y', 0)})"
                    
                    commentary.append(action_desc)
                    logger.info(f"Executing: {action_desc}")
                    
                    # If no reasoning is available, generate one 
                    if not hasattr(self, 'last_reasoning') or not self.last_reasoning:
                        self.last_reasoning = self.generate_action_reasoning(action_type, action)
                        logger.debug(f"Generated reasoning: {self.last_reasoning}")
                        results.append(f"💡 Generated reasoning: {self.last_reasoning}")
                    
                    # Show reasoning alongside action for better context
                    if self.last_reasoning:
                        results.append(f"💭 Action context: {self.last_reasoning}")
                    
                    # Execute the computer action
                    try:
                        # Log the action with full details for troubleshooting
                        if action_type == "click":
                            x, y = action.get("x", 0), action.get("y", 0)
                            logger.info(f"Executing click at coordinates: ({x}, {y})")
                        
                        result_text = await self.execute_computer_action(action)
                        results.append(f"✅ {action_desc} - {result_text}")
                        
                        # Add a brief delay after action execution
                        await asyncio.sleep(0.3)
                    except Exception as e:
                        error_msg = f"Error in {action_type}: {str(e)}"
                        logger.error(error_msg)
                        results.append(f"❌ {action_desc} - {error_msg}")
                        # On error, we'll stop and not continue
                        continue_execution = False
                        break
                    
                    # Preserve reasoning for next action if needed
                    self.last_reasoning = None
            
            # If we performed actions and should continue executing more actions, call the API again with updated state
            if continue_execution and actions_in_this_iteration > 0 and iterations < max_iterations:
                # Take a new screenshot and prepare for next iteration
                logger.info(f"Executed {actions_in_this_iteration} action(s) in this iteration. Taking new screenshot and continuing...")
                
                # Add a sufficient delay to ensure the browser has time to update fully (DOM changes, page transitions)
                await asyncio.sleep(1.0)
                
                # Check if the page URL has changed since the start of this iteration
                current_url = await self.browser_instance.get_current_url()
                logger.info(f"Current URL after actions: {current_url}")
                
                # Take a browser status snapshot for debugging
                try:
                    title = await self.browser_instance.page.title()
                    # Count elements as a rough measure of page readiness
                    element_count = await self.browser_instance.page.evaluate("document.querySelectorAll('*').length")
                    logger.info(f"Page state: {element_count} elements, title: {title}")
                except Exception as e:
                    logger.error(f"Could not get page state: {str(e)}")
                
                # Take a new screenshot for the next iteration
                screenshot = await self.browser_instance.take_screenshot()
                
                # Create a clean message to continue the task
                try:
                    logger.info("Getting next actions from CUA API...")
                    # Create a clean system message with stronger directions
                    system_message = {
                        "role": "system", 
                        "content": """You control a Chrome browser and need to help users accomplish tasks step by step.
IMPORTANT: You must ALWAYS use computer actions (click, type, scroll, etc.) rather than just describing what to do.
DO NOT wait for confirmation before taking the next action - you should continuously perform actions until the task is complete.
Your goal is to complete the user's task through direct manipulation of the browser.
If you understand a task, start acting on it immediately. Do not ask for clarification unless absolutely necessary.
"""
                    }
                    
                    # Keep original instruction from the user's initial request
                    original_instruction = ""
                    if len(self.conversation) >= 2 and self.conversation[1].get("role") == "user":
                        for content_item in self.conversation[1].get("content", []):
                            if content_item.get("type") == "input_text":
                                original_instruction = content_item.get("text", "")
                                break
                    
                    # Extract the core instruction, skipping the step-by-step guidance we added
                    if "\n\nI need you to help me complete this task" in original_instruction:
                        original_instruction = original_instruction.split("\n\nI need you to help me complete this task")[0]
                    
                    # Reset conversation for the continuation call, but include the original instruction
                    self.conversation = [system_message]
                        
                    # Create a continuation message that explicitly directs continuing with actions
                    # Add more context about what we've done so far to help it continue coherently
                    
                    # Get the page title to provide more context
                    page_title = ""
                    try:
                        page_title = await self.browser_instance.page.title()
                    except:
                        page_title = "Unknown page"
                    
                    # Get more detailed page state information for better context
                    try:
                        # Enhanced page analysis with more detailed information about UI elements
                        page_info = await self.browser_instance.page.evaluate("""() => {
                            // Helper function to check if element is visible in viewport
                            const isVisible = (el) => {
                                if (!el) return false;
                                const rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0 && 
                                       rect.top >= 0 && rect.left >= 0 && 
                                       rect.bottom <= window.innerHeight && rect.right <= window.innerWidth;
                            };
                            
                            // Helper to get coordinates of element
                            const getCoords = (el) => {
                                if (!el) return null;
                                const rect = el.getBoundingClientRect();
                                return {
                                    x: Math.floor(rect.left + rect.width/2),
                                    y: Math.floor(rect.top + rect.height/2)
                                };
                            };
                            
                            // Find key UI elements with coordinates
                            const searchBar = document.querySelector('input[type="search"], input[type="text"][name*="search"], input[placeholder*="search"]');
                            const searchButton = document.querySelector('button[type="submit"], button[aria-label*="search" i], input[type="submit"]');
                            
                            // Find add to cart buttons
                            const addToCartButtons = Array.from(document.querySelectorAll('button, a')).filter(el => {
                                const text = (el.textContent || '').toLowerCase();
                                return text.includes('add to cart') || 
                                      text.includes('add to bag') || 
                                      text.includes('add to basket') ||
                                      text.includes('buy now');
                            });
                            
                            // Find search inputs with their coordinates
                            const searchInputs = Array.from(document.querySelectorAll('input[type="search"], input[type="text"][name*="search"], input[placeholder*="search"]'))
                                .filter(isVisible)
                                .map(el => ({
                                    placeholder: el.placeholder || '',
                                    coords: getCoords(el)
                                }));
                                
                            // Get visible links and buttons with text and coordinates
                            const importantButtons = Array.from(document.querySelectorAll('button, a.button, [role="button"]'))
                                .filter(isVisible)
                                .filter(el => el.innerText.trim().length > 0)
                                .map(el => ({
                                    text: el.innerText.trim().substring(0, 30),
                                    coords: getCoords(el)
                                }))
                                .slice(0, 5);
                                
                            const importantLinks = Array.from(document.querySelectorAll('a'))
                                .filter(isVisible)
                                .filter(el => el.innerText.trim().length > 0)
                                .map(el => ({
                                    text: el.innerText.trim().substring(0, 30),
                                    coords: getCoords(el)
                                }))
                                .slice(0, 5);
                            
                            // Identify address bar locations for browsers
                            const isGoogle = window.location.hostname.includes('google');
                            const addressBarCoords = isGoogle ? getCoords(document.querySelector('input[type="text"]')) : null;
                            
                            // Determine page type
                            const isProductPage = document.body.innerHTML.toLowerCase().includes('add to cart') ||
                                                 document.body.innerHTML.toLowerCase().includes('product details') ||
                                                 document.body.innerText.toLowerCase().includes('price:');
                                                 
                            const isSearchResults = document.title.toLowerCase().includes('search') || 
                                                  document.body.innerText.toLowerCase().includes('search results') ||
                                                  document.body.innerText.toLowerCase().includes('items found');
                                                  
                            const isCheckout = document.body.innerHTML.toLowerCase().includes('checkout') ||
                                             document.body.innerHTML.toLowerCase().includes('payment') ||
                                             document.body.innerHTML.toLowerCase().includes('shipping');
                                             
                            return {
                                url: window.location.href,
                                title: document.title,
                                isGoogle: isGoogle,
                                addressBarCoords: addressBarCoords,
                                searchBarCoords: getCoords(searchBar),
                                searchButtonCoords: getCoords(searchButton),
                                searchInputs: searchInputs,
                                importantButtons: importantButtons,
                                importantLinks: importantLinks,
                                addToCartCoords: addToCartButtons.length > 0 ? getCoords(addToCartButtons[0]) : null,
                                isProductPage: isProductPage,
                                isSearchResults: isSearchResults,
                                isCheckout: isCheckout,
                                pageHeading: document.querySelector('h1')?.innerText || '',
                                formCount: document.forms.length,
                            };
                        }""")
                        logger.info(f"Detailed page analysis for continuation: {page_info}")
                    except Exception as e:
                        logger.warning(f"Could not get detailed page info: {e}")
                        page_info = {}
                    
                    # Summarize the actions we've performed so far for context (last 10 actions max)
                    actions_summary = "\n".join(commentary[-min(10, len(commentary)):])
                    
                    # Format coordinate info for key UI elements to provide direct guidance
                    clickable_elements = []
                    try:
                        # Add search bar coordinates if available
                        if page_info.get('searchBarCoords'):
                            coords = page_info.get('searchBarCoords')
                            clickable_elements.append(f"• Search bar: ({coords['x']}, {coords['y']})")
                            
                        # Add search button coordinates if available
                        if page_info.get('searchButtonCoords'):
                            coords = page_info.get('searchButtonCoords')
                            clickable_elements.append(f"• Search button: ({coords['x']}, {coords['y']})")
                            
                        # Add address bar coordinates if on Google
                        if page_info.get('isGoogle') and page_info.get('addressBarCoords'):
                            coords = page_info.get('addressBarCoords')
                            clickable_elements.append(f"• Address bar: ({coords['x']}, {coords['y']})")
                            
                        # Add Add to Cart button if on product page
                        if page_info.get('isProductPage') and page_info.get('addToCartCoords'):
                            coords = page_info.get('addToCartCoords')
                            clickable_elements.append(f"• Add to Cart button: ({coords['x']}, {coords['y']})")
                            
                        # Add important buttons with coordinates
                        if 'importantButtons' in page_info and page_info.get('importantButtons'):
                            for button in page_info.get('importantButtons'):
                                if button.get('coords'):
                                    clickable_elements.append(f"• Button '{button.get('text')}': ({button.get('coords').get('x')}, {button.get('coords').get('y')})")
                                    
                        # Add important links with coordinates
                        if 'importantLinks' in page_info and page_info.get('importantLinks'):
                            for link in page_info.get('importantLinks'):
                                if link.get('coords'):
                                    clickable_elements.append(f"• Link '{link.get('text')}': ({link.get('coords').get('x')}, {link.get('coords').get('y')})")
                    except Exception as e:
                        logger.warning(f"Error formatting clickable elements: {e}")
                    
                    clickable_elements_text = "\n".join(clickable_elements) if clickable_elements else "No clickable elements detected"
                    
                    # Determine page type for better context
                    page_type = "unknown"
                    if page_info.get('isGoogle', False):
                        page_type = "Google homepage"
                    elif page_info.get('isProductPage', False):
                        page_type = "product page"
                    elif page_info.get('isSearchResults', False):
                        page_type = "search results page"
                    elif page_info.get('isCheckout', False):
                        page_type = "checkout page"
                        
                    # Create concise page context
                    page_context = f"""CURRENT PAGE:
• URL: {current_url}
• Title: {page_title}
• Type: {page_type}
• Heading: {page_info.get('pageHeading', 'None')}

CLICKABLE ELEMENTS WITH COORDINATES:
{clickable_elements_text}
"""
                    
                    # Determine if we're stuck by examining recent actions
                    stuck_detection = ""
                    repeated_clicks = []
                    for comment in commentary[-10:]:
                        if "Clicking at (" in comment:
                            coords = comment.split("Clicking at (")[1].split(")")[0]
                            repeated_clicks.append(coords)
                    
                    # Count occurrence of each coordinate
                    from collections import Counter
                    click_counts = Counter(repeated_clicks)
                    
                    # If any coordinate was clicked more than twice, we're likely stuck
                    stuck_coords = [(coord, count) for coord, count in click_counts.items() if count > 2]
                    if stuck_coords:
                        stuck_detection = f"""⚠️ STUCK DETECTION: You're repeating the same click at {stuck_coords[0][0]} ({stuck_coords[0][1]} times).

TRY THESE ALTERNATIVE APPROACHES:
1. Use "goto" with a FULL URL: {{"type": "goto", "url": "https://example.com"}}
2. Click at a completely different location
3. Try a different action type (type, scroll, keypress)

"""
                        # Add context-specific suggestions
                        if "google.com" in current_url:
                            stuck_detection += """SPECIFIC SUGGESTION: Use goto directly: {"type": "goto", "url": "https://amazon.com"}"""
                        elif any(site in current_url for site in ["amazon", "walmart", "ebay", "shop"]):
                            # If on a shopping site but stuck
                            if "search" in current_url.lower():
                                stuck_detection += """SPECIFIC SUGGESTION: Click on a specific product listing (not the same spot)"""
                            else:
                                stuck_detection += """SPECIFIC SUGGESTION: Look for and click on the search box, then type your query"""
                    
                    # Create the continuation message with clear, focused guidance
                    continuation_message = {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{screenshot}"
                            },
                            {
                                "type": "input_text",
                                "text": f"""CONTINUE THE TASK: {original_instruction}

RECENT ACTIONS:
{actions_summary}

{page_context}

{stuck_detection}

INSTRUCTIONS:
1. Take the IMMEDIATE NEXT ACTION (goto, click, type, scroll)
2. DO NOT describe what you're doing - JUST PERFORM the action
3. Use goto with FULL URLs (https://site.com) for navigation
4. If your current strategy isn't working, try something completely different

EXECUTE THE NEXT ACTION NOW:
"""
                            }
                        ]
                    }
                    
                    self.conversation.append(continuation_message)
                    
                    # Call the API again
                    url = "https://api.openai.com/v1/responses"
                    headers = {
                        "Authorization": f"Bearer {self.openai_api_key}",
                        "Content-Type": "application/json",
                        "Openai-Beta": "responses=v1"
                    }
                    
                    openai_org = os.environ.get("OPENAI_ORG")
                    if openai_org:
                        headers["OpenAI-Organization"] = openai_org
                    
                    # Prepare API payload with same tools
                    tools = [
                        {
                            "type": "computer-preview",
                            "display_width": self.browser_instance.dimensions[0],
                            "display_height": self.browser_instance.dimensions[1],
                            "environment": "browser"
                        }
                    ]
                    
                    payload = {
                        "model": "computer-use-preview",
                        "input": self.conversation,
                        "tools": tools,
                        "truncation": "auto",
                        "temperature": 0.2
                    }
                    
                    # API request with timeout
                    async with aiohttp.ClientSession() as session:
                        try:
                            logger.info("Requesting next actions from CUA API...")
                            async with session.post(url, headers=headers, json=payload) as response:
                                if response.status != 200:
                                    error_text = await response.text()
                                    logger.error(f"Continuation API Error: {error_text}")
                                    continue_execution = False
                                else:
                                    response_text = await response.text()
                                    result = json.loads(response_text)
                                    if "output" in result:
                                        # Update the items to process and continue the loop
                                        items = result["output"]
                                        logger.info(f"Received {len(items)} new items to process")
                                    else:
                                        logger.warning("No output in continuation response")
                                        continue_execution = False
                        except Exception as e:
                            logger.error(f"Error in continuation API call: {str(e)}")
                            continue_execution = False
                except Exception as e:
                    logger.error(f"Error preparing continuation: {str(e)}")
                    continue_execution = False
            else:
                # No actions performed in this iteration or hit max iterations
                if actions_in_this_iteration == 0:
                    logger.info("No actions executed in this iteration, stopping continuation")
                continue_execution = False
        
        # Take a final screenshot 
        final_screenshot = await self.browser_instance.take_screenshot()
        current_url = await self.browser_instance.get_current_url()
        
        # Build a better summary text
        if not final_text:
            if messages_received > 0:
                final_text = "Task completed. Here's what happened:"
            else:
                final_text = "Actions completed without additional commentary."
        
        # Build summary statistics
        summary = [
            f"• Executed {actions_executed} browser actions",
            f"• Current page: {current_url}" if current_url else "",
            f"• Task status: {'Completed' if final_text else 'In progress'}",
            f"• Iterations: {iterations}"
        ]
        
        # Join all results for a comprehensive response text
        detailed_log = "\n".join(results) if results else "No actions were executed."
        
        # Create a clean, readable summary text
        text_result = (
            f"{final_text}\n\n"
            f"📋 Summary:\n{chr(10).join(s for s in summary if s)}\n\n"
            f"🔍 Actions performed:\n{detailed_log}"
        )
            
        return {
            "text": text_result,
            "screenshot": final_screenshot,
            "actions_executed": actions_executed
        }
    
    async def execute_computer_action(self, action):
        """Execute a computer action from the Computer Use API."""
        if not self.browser_instance.page:
            return "Browser not initialized"
        
        action_type = action.get("type")
        logger.info(f"Executing action: {action_type} with params: {action}")
        
        try:
            # Ensure the page is stable before proceeding with any action
            await asyncio.sleep(0.2)
            
            if action_type == "click":
                x = action.get("x", 0)
                y = action.get("y", 0)
                button = action.get("button", "left")
                
                if button == "back":
                    await self.browser_instance.page.go_back()
                    await asyncio.sleep(0.5)  # Increased wait to ensure navigation starts
                    return "Went back to previous page"
                elif button == "forward":
                    await self.browser_instance.page.go_forward()
                    await asyncio.sleep(0.5)  # Increased wait to ensure navigation starts
                    return "Went forward to next page"
                else:
                    button_mapping = {"left": "left", "right": "right", "middle": "middle"}
                    button_type = button_mapping.get(button, "left")
                    
                    # Get element at position for better logging
                    try:
                        element_info = await self.browser_instance.page.evaluate("""
                            (x, y) => {
                                const element = document.elementFromPoint(x, y);
                                if (!element) return null;
                                
                                // Get useful info about what we're clicking
                                return {
                                    tag: element.tagName,
                                    id: element.id,
                                    className: element.className,
                                    text: element.innerText ? element.innerText.substring(0, 50) : '',
                                    isLink: element.tagName === 'A' || element.closest('a') !== null,
                                    isButton: element.tagName === 'BUTTON' || 
                                             element.getAttribute('role') === 'button' ||
                                             element.closest('button') !== null,
                                    isInput: element.tagName === 'INPUT' || element.tagName === 'TEXTAREA'
                                };
                            }
                        """, x, y)
                        
                        if element_info:
                            logger.info(f"Clicking on element: {element_info}")
                    except Exception as e:
                        logger.debug(f"Could not get element info: {str(e)}")
                        element_info = None
                    
                    # Use Playwright's mouse.click() for reliable clicking
                    logger.info(f"Clicking at position ({x}, {y}) with {button} button")
                    await self.browser_instance.page.mouse.click(x, y, button=button_type)
                    
                    # Wait for click to be processed
                    await asyncio.sleep(0.5)
                    
                    # Set up navigation listener for more accurate detection
                    try:
                        # Check if click triggered navigation or page changes
                        url_before = self.browser_instance.page.url
                        logger.info(f"URL before click: {url_before}")
                        
                        # Wait longer to catch slower navigation starts
                        await asyncio.sleep(1.0)
                        
                        # Check both URL changes and page loading state
                        url_after = self.browser_instance.page.url
                        logger.info(f"URL after click: {url_after}")
                        
                        if url_before != url_after:
                            logger.info(f"Click initiated navigation from {url_before} to {url_after}")
                            # Now wait for loading to complete
                            try:
                                await self.browser_instance.page.wait_for_load_state('domcontentloaded', timeout=10000)
                                logger.info("Navigation completed to domcontentloaded state")
                                # Additional wait for network idle
                                try:
                                    await self.browser_instance.page.wait_for_load_state('networkidle', timeout=5000) 
                                    logger.info("Network is now idle after navigation")
                                except:
                                    logger.info("Network didn't reach idle state, but page is usable")
                            except Exception as nav_error:
                                logger.warning(f"Navigation may not have completed fully: {nav_error}")
                        else:
                            # Even if URL didn't change, check if the page is processing new content
                            try:
                                loading_state = await self.browser_instance.page.evaluate("document.readyState")
                                logger.info(f"Document readyState after click: {loading_state}")
                                if loading_state != 'complete':
                                    # Wait for completion if not already complete
                                    await self.browser_instance.page.wait_for_load_state('domcontentloaded', timeout=5000)
                            except Exception as e:
                                logger.debug(f"State check error (non-critical): {str(e)}")
                    except Exception as e:
                        # Ignore errors in navigation check
                        logger.debug(f"Navigation check error (non-critical): {str(e)}")
                    
                    # Provide a more informative return message
                    element_desc = ""
                    if element_info:
                        if element_info.get('isLink'):
                            element_desc = " on a link"
                        elif element_info.get('isButton'):
                            element_desc = " on a button"
                        elif element_info.get('isInput'):
                            element_desc = " on an input field"
                        elif element_info.get('text'):
                            text = element_info.get('text', '').strip()
                            if text:
                                element_desc = f" on element with text: {text[:30]}"
                    
                    return f"Clicked at ({x}, {y}){element_desc} with {button} button"
            
            elif action_type == "double_click":
                x = action.get("x", 0)
                y = action.get("y", 0)
                
                # Use Playwright's dblclick method - simpler and more reliable
                await self.browser_instance.page.mouse.dblclick(x, y)
                
                # Wait for double-click to be processed
                await asyncio.sleep(0.5)
                
                return f"Double-clicked at ({x}, {y})"
                
            elif action_type == "type":
                text = action.get("text", "")
                
                # Following Klick-genome approach - use a small but reasonable delay
                # 5ms is usually too small for real-world applications
                # But not so long that it feels abnormally slow
                await self.browser_instance.page.keyboard.type(text, delay=25)
                
                # Wait a bit after typing to ensure text is processed
                await asyncio.sleep(0.5)
                
                return f"Typed: {text}"
                
            elif action_type == "keypress":
                keys = action.get("keys", [])
                for key in keys:
                    # Press with proper down/up events
                    await self.browser_instance.page.keyboard.down(key)
                    await asyncio.sleep(0.05)
                    await self.browser_instance.page.keyboard.up(key)
                    await asyncio.sleep(0.1)
                    
                return f"Pressed keys: {', '.join(keys)}"
                
            elif action_type == "goto":
                url = action.get("url", "")
                if not url:
                    return "No URL provided for goto action"
                
                # Add missing protocol if needed
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = "https://" + url
                    logger.info(f"Added https:// prefix to URL: {url}")
                
                if check_blocklisted_url(url):
                    return f"Access to {url} is blocked for safety reasons"
                
                # Improved navigation with robust error handling
                try:
                    logger.info(f"Navigating to {url}")
                    
                    # Step 1: Start navigation with appropriate timeout and wait state
                    # We use domcontentloaded instead of load to be more responsive
                    navigation_promise = self.browser_instance.page.goto(
                        url, 
                        wait_until='domcontentloaded', 
                        timeout=25000
                    )
                    
                    # Add a reasonable timeout to avoid infinite waits
                    try:
                        response = await asyncio.wait_for(navigation_promise, timeout=30)
                        
                        # Step 2: Check if we got a valid response
                        if response and hasattr(response, 'status') and response.status >= 400:
                            logger.warning(f"Received error status {response.status} when navigating to {url}")
                    except asyncio.TimeoutError:
                        logger.warning(f"Navigation to {url} timed out at wait_for level, proceeding with partial load")
                    
                    # Step 3: Wait briefly for page to stabilize
                    await asyncio.sleep(0.5)
                    
                    # Step 4: Try to wait for network to become idle, but don't block progress if it takes too long
                    try:
                        await asyncio.wait_for(
                            self.browser_instance.page.wait_for_load_state('networkidle'), 
                            timeout=5
                        )
                        logger.info(f"Network is idle for {url}")
                    except asyncio.TimeoutError:
                        logger.info(f"Network didn't become idle within timeout window for {url}, but continuing")
                    except Exception as idle_error:
                        logger.warning(f"Error waiting for network idle: {idle_error}")
                    
                    # Step 5: Final wait for any JavaScript initialization
                    await asyncio.sleep(1.0)
                    
                    # Step 6: Check final state
                    final_url = self.browser_instance.page.url
                    
                    # Check if we were redirected
                    if final_url != url:
                        logger.info(f"Redirected from {url} to {final_url}")
                    
                    # Verify page is responsive by checking document state
                    try:
                        ready_state = await asyncio.wait_for(
                            self.browser_instance.page.evaluate("document.readyState"),
                            timeout=2
                        )
                        logger.info(f"Document readyState: {ready_state}")
                        
                        # Extra verification: check if key DOM elements exist
                        element_count = await self.browser_instance.page.evaluate("document.querySelectorAll('*').length")
                        logger.info(f"Page has {element_count} DOM elements")
                        
                        return f"Successfully navigated to: {final_url} (readyState: {ready_state}, elements: {element_count})"
                    except Exception as verify_err:
                        logger.warning(f"Could not verify page state: {verify_err}")
                        return f"Navigated to: {final_url} (verification failed)"
                        
                except Exception as nav_error:
                    logger.error(f"Navigation error: {nav_error}")
                    
                    # Attempt recovery with fallback strategy
                    try:
                        # Check if we're on the page despite the error
                        current_url = self.browser_instance.page.url
                        if url in current_url or current_url != "about:blank":
                            logger.info(f"Page partially loaded despite error, current URL: {current_url}")
                            return f"Partial navigation to: {current_url} (after error)"
                            
                        # Try an alternate, more direct navigation approach
                        logger.info(f"Attempting alternate navigation method to {url}")
                        
                        # Try direct evaluate approach as fallback
                        await self.browser_instance.page.evaluate(f"window.location.href = '{url}'")
                        await asyncio.sleep(3)  # Wait longer for redirect to take effect
                        
                        backup_url = self.browser_instance.page.url
                        if backup_url != "about:blank" and backup_url != current_url:
                            return f"Navigated to {backup_url} using backup method"
                    except Exception as recovery_err:
                        logger.error(f"Recovery attempt failed: {recovery_err}")
                    
                    # If all else fails
                    return f"Failed to navigate to: {url}"
                
            elif action_type == "wait":
                ms = action.get("ms", 1000)
                await asyncio.sleep(ms / 1000)
                return f"Waited for {ms} ms"
                
            elif action_type == "scroll":
                x = action.get("x", 0)
                y = action.get("y", 0)
                scroll_x = action.get("scroll_x", 0)
                scroll_y = action.get("scroll_y", 0)
                
                # Position mouse first
                await self.browser_instance.page.mouse.move(x, y)
                await asyncio.sleep(0.1)
                
                # Then scroll with JavaScript for reliability
                await self.browser_instance.page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")
                
                # Give time for scroll to finish
                await asyncio.sleep(0.3)
                
                return f"Scrolled by ({scroll_x}, {scroll_y}) from position ({x}, {y})"
                
            elif action_type == "move":
                x = action.get("x", 0)
                y = action.get("y", 0)
                await self.browser_instance.page.mouse.move(x, y)
                await asyncio.sleep(0.1)  # Brief wait after move
                return f"Moved mouse to ({x}, {y})"
                
            elif action_type == "drag":
                path = action.get("path", [])
                if not path:
                    return "No path provided for drag action"
                
                # First move to start position
                await self.browser_instance.page.mouse.move(path[0].get("x", 0), path[0].get("y", 0))
                await asyncio.sleep(0.1)
                
                # Proper drag sequence with timing
                await self.browser_instance.page.mouse.down()
                await asyncio.sleep(0.1)
                
                # Move through path with realistic timing
                for point in path[1:]:
                    await self.browser_instance.page.mouse.move(point.get("x", 0), point.get("y", 0))
                    await asyncio.sleep(0.05)
                    
                # Complete the drag
                await asyncio.sleep(0.1)
                await self.browser_instance.page.mouse.up()
                
                return f"Dragged from ({path[0].get('x', 0)}, {path[0].get('y', 0)}) to ({path[-1].get('x', 0)}, {path[-1].get('y', 0)})"
            
            elif action_type == "screenshot":
                # This isn't a real action, but we'll handle it gracefully
                return "Taking screenshot (handled automatically)"
                
            else:
                return f"Unknown action type: {action_type}"
                
        except Exception as e:
            error_msg = f"Error executing {action_type} action: {str(e)}"
            logger.error(error_msg)
            import traceback
            error_tb = traceback.format_exc()
            logger.error(error_tb)
            return error_msg
        
    async def process_message(self, message: str) -> dict:
        """Process a user message and operate the browser accordingly."""
        # Take a screenshot of the current state
        screenshot = await self.browser_instance.take_screenshot()
        if not screenshot:
            return {"text": "Could not take screenshot. Is the browser initialized?"}
        
        # Get the current URL directly from the page object to avoid triggering state operations
        current_url = self.browser_instance.page.url if self.browser_instance.page else ""
        
        # Reset conversation for each message to avoid multiple image issues with CUA API
        # Use a clearer, more direct system message to help the Computer Use API understand its role
        self.conversation = [
            {
                "role": "system", 
                "content": """You control a Chrome browser to accomplish web tasks.

TASK COMPLETION COMMANDS:
- goto: {"type": "goto", "url": "https://example.com"} - Always use complete URLs with https://
- click: {"type": "click", "x": 100, "y": 200} - Click at specific coordinates
- type: {"type": "type", "text": "search query"} - Type text
- keypress: {"type": "keypress", "keys": ["Enter"]} - Press specific keys
- scroll: {"type": "scroll", "x": 0, "y": 0, "scroll_x": 0, "scroll_y": 500} - Scroll the page

NAVIGATION PRIORITY:
1. ALWAYS use goto with full URL first: {"type": "goto", "url": "https://amazon.com"}
2. NEVER type partial URLs - always include https:// prefix
3. If direct goto fails, go to google.com first, then search for the website

COMPLETE MULTI-STEP TASKS:
- Take actions continuously without asking for permission
- Complete ALL steps of a task, not just the first step
- If one approach doesn't work, try a completely different approach
- Observe the page after each action and decide the next appropriate step

You MUST ONLY respond with computer actions, not explanations.
"""
            }
        ]
        
        # Create user message with clearer instructions for multi-step flows
        # Get page details for context
        page_title = ""
        try:
            page_title = await self.browser_instance.page.title()
        except Exception:
            page_title = "Unknown page"
        
        # Get more page details to help with task understanding
        try:
            page_elements = await self.browser_instance.page.evaluate("""() => {
                // Gather key page elements and info
                const isSearchInputVisible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && 
                           rect.top >= 0 && rect.left >= 0 && 
                           rect.bottom <= window.innerHeight && rect.right <= window.innerWidth;
                };
                
                // Find search inputs
                const searchInputs = Array.from(document.querySelectorAll('input[type="search"], input[type="text"][name*="search"], input[type="text"][placeholder*="search"]'))
                    .filter(isSearchInputVisible);
                
                // Find clickable elements
                const buttons = Array.from(document.querySelectorAll('button')).filter(isSearchInputVisible);
                const links = Array.from(document.querySelectorAll('a')).filter(isSearchInputVisible);
                
                // Identify common UI elements
                const searchBar = document.querySelector('input[type="search"], input[type="text"][placeholder*="search"]');
                const searchButton = searchBar ? 
                    document.querySelector('button[type="submit"]') || 
                    searchBar.closest('form')?.querySelector('button') : null;
                const searchForm = searchBar?.closest('form');
                
                // Identify page type based on content
                const hasProductElements = document.body.innerHTML.toLowerCase().includes('add to cart') ||
                                          document.body.innerHTML.toLowerCase().includes('product details') ||
                                          document.body.innerText.toLowerCase().includes('price:');
                                          
                const isSearchResults = document.title.toLowerCase().includes('search') || 
                                       document.body.innerText.toLowerCase().includes('search results') ||
                                       document.body.innerText.toLowerCase().includes('items found');
                
                // Identify address bar location if on Google
                const isGoogle = window.location.hostname.includes('google');
                const addressBarY = isGoogle ? document.querySelector('input[type="text"]')?.getBoundingClientRect().top + 20 : null;
                
                return {
                    title: document.title,
                    url: window.location.href,
                    isGoogle: isGoogle,
                    searchInputCount: searchInputs.length,
                    buttonCount: buttons.length,
                    linkCount: links.length,
                    hasSearchBar: !!searchBar,
                    hasSearchButton: !!searchButton,
                    hasSearchForm: !!searchForm,
                    isProductPage: hasProductElements,
                    isSearchResults: isSearchResults,
                    addressBarY: addressBarY,
                    mainHeading: document.querySelector('h1')?.innerText || '',
                    visibleText: Array.from(document.querySelectorAll('h1, h2, h3, button'))
                                  .filter(isSearchInputVisible)
                                  .map(el => el.innerText.trim())
                                  .filter(text => text.length > 0)
                                  .slice(0, 5)
                };
            }""")
        except Exception as e:
            logger.warning(f"Failed to get page elements: {e}")
            page_elements = {}
        
        # Build page context string
        page_info = ""
        if isinstance(page_elements, dict):
            page_type = "unknown"
            if page_elements.get("isGoogle", False):
                page_type = "Google homepage"
            elif page_elements.get("isProductPage", False):
                page_type = "product page"
            elif page_elements.get("isSearchResults", False):
                page_type = "search results page"
            
            key_ui_info = ""
            if page_elements.get("hasSearchBar", False):
                key_ui_info += "• The page has a search bar\n"
            if page_elements.get("hasSearchButton", False):
                key_ui_info += "• The page has a search button\n"
            if "addressBarY" in page_elements and page_elements["addressBarY"]:
                key_ui_info += f"• Address bar is located around y-coordinate: {page_elements['addressBarY']}\n"
            
            visible_elements = page_elements.get("visibleText", [])
            visible_text = "\n".join(f"• {text}" for text in visible_elements) if visible_elements else "• No prominent text elements found"
            
            page_info = f"""CURRENT PAGE INFO:
• URL: {current_url}
• Title: {page_title}
• Page type: {page_type}
• Main heading: {page_elements.get('mainHeading', 'None')}

KEY UI ELEMENTS:
{key_ui_info}• Buttons: {page_elements.get('buttonCount', 0)}
• Links: {page_elements.get('linkCount', 0)}
• Search inputs: {page_elements.get('searchInputCount', 0)}

VISIBLE TEXT ELEMENTS:
{visible_text}
"""
        else:
            page_info = f"""CURRENT PAGE INFO:
• URL: {current_url}
• Title: {page_title}
"""
        
        # Create the user message with task, page info, and clear instructions
        user_message = {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot}"
                },
                {
                    "type": "input_text",
                    "text": f"""TASK: {message}

{page_info}

IMPORTANT INSTRUCTIONS:
1. ALWAYS start with the "goto" action using a full URL when navigating to a new site
2. Execute the COMPLETE task by taking multiple actions in sequence
3. DO NOT EXPLAIN your actions - just execute the next appropriate action
4. If the current approach isn't working, try a completely different approach
5. Continue taking actions until the entire task is completed

EXECUTE THE FIRST ACTION IMMEDIATELY.
"""
                }
            ]
        }
        
        # Add the user message to conversation
        self.conversation.append(user_message)
        
        # Call the OpenAI Computer Use API with a timeout
        try:
            logger.info(f"Calling Computer Use API to process: {message}")
            api_task = asyncio.create_task(
                self.call_computer_use_api(message, screenshot, current_url)
            )
            
            # Wait for API call with timeout (90 seconds)
            result = await asyncio.wait_for(api_task, timeout=90)
            logger.info(f"API processing complete. Actions executed: {result.get('actions_executed', 0)}")
            return result
        except asyncio.TimeoutError:
            logger.error("CUA API call timed out after 90 seconds")
            return {
                "text": "Operation timed out after 90 seconds. The request may have been too complex or the API is experiencing delays.",
                "screenshot": screenshot
            }
        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}")
            return {
                "text": f"Error processing the operation: {str(e)}",
                "screenshot": screenshot
            }
    
    async def close(self):
        """Close the browser operator."""
        await self.browser_instance.close()
        self.conversation = []