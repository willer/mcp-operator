#!/usr/bin/env python3

import asyncio
import base64
import json
import os
import re
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse

import aiohttp
import dotenv
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

# Load environment variables
dotenv.load_dotenv()

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
    """A class to manage a browser instance using Playwright."""
    
    def __init__(self, browser_id: str, dimensions: Tuple[int, int] = (1024, 768)):
        self.browser_id = browser_id
        self.dimensions = dimensions
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.current_conversation = []
        
    async def initialize(self):
        """Initialize the browser instance."""
        width, height = self.dimensions
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            args=[f"--window-size={width},{height}", "--disable-extensions"]
        )
        self.context = await self.browser.new_context()
        
        # Set up event listener for URL blocking
        async def handle_route(route, request):
            url = request.url
            if check_blocklisted_url(url):
                print(f"Blocking access to: {url}")
                await route.abort()
            else:
                await route.continue_()
                
        await self.context.route("**/*", handle_route)
        
        self.page = await self.context.new_page()
        await self.page.set_viewport_size({"width": width, "height": height})
        await self.page.goto("https://google.com")
        
    async def take_screenshot(self) -> Optional[str]:
        """Take a screenshot of the current page."""
        if not self.page:
            return None
        
        try:
            screenshot_bytes = await self.page.screenshot(full_page=False)
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as e:
            print(f"Screenshot error: {str(e)}")
            return None
    
    async def get_current_url(self) -> str:
        """Get the current URL of the page."""
        if not self.page:
            return ""
        return self.page.url
        
    async def close(self):
        """Close the browser instance."""
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
    
    def __init__(self, browser_id: str):
        self.browser_id = browser_id
        self.browser_instance = BrowserInstance(browser_id)
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not self.openai_api_key:
            print("WARNING: OPENAI_API_KEY environment variable not set! Computer Use API will not work.")
        self.conversation = []
        self.last_reasoning = None  # Store reasoning for better action context
        self.print_steps = True     # Print steps for debugging
        
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
            print(f"Yahoo.com detected, using reduced wait state approach")
            
            try:
                # Set a shorter timeout for initial navigation
                navigate_future = asyncio.ensure_future(
                    self.browser_instance.page.goto(url, timeout=15000, wait_until='domcontentloaded')
                )
                
                try:
                    # Wait but don't block too long
                    await asyncio.wait_for(navigate_future, timeout=20)
                except asyncio.TimeoutError:
                    print("Navigation timeout, but continuing...")
                    # Even with timeout, we can still get a screenshot
                
                # Take screenshot of whatever state we reached
                await asyncio.sleep(1)  # Brief pause to let rendering happen
                screenshot = await self.browser_instance.take_screenshot()
                return {
                    "text": f"Attempted navigation to {url} (Yahoo sites may load slowly)",
                    "screenshot": screenshot
                }
            except Exception as e:
                print(f"Navigation error with yahoo: {str(e)}")
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
            print(f"Navigating to {url}...")
            
            timeout_task = asyncio.create_task(
                self.browser_instance.page.goto(url, timeout=20000, wait_until='domcontentloaded')
            )
            
            # Wait for navigation with timeout
            try:
                await asyncio.wait_for(timeout_task, timeout=25)
                print(f"Navigation to {url} completed")
            except asyncio.TimeoutError:
                print(f"Navigation to {url} timed out, but proceeding with partial load")
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
            print(f"Navigation error: {str(e)}")
            # Try to get a screenshot even if navigation had an error
            try:
                screenshot = await self.browser_instance.take_screenshot()
                return {
                    "text": f"Error navigating to {url}: {str(e)}",
                    "screenshot": screenshot
                }
            except Exception as screenshot_err:
                print(f"Error taking screenshot: {str(screenshot_err)}")
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
        
        # Format the user message with the current screenshot and request using correct type
        # IMPORTANT: Only include one image in the entire conversation to avoid API errors
        # Clear previous conversation entries, keeping only system message if present
        if self.conversation and self.conversation[0].get("role") == "system":
            system_message = self.conversation[0]
            self.conversation = [system_message]
        else:
            self.conversation = []
            
        # Create new message with combined content
        new_message = {
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot}"
                },
                {
                    "type": "input_text",
                    "text": f"""
{user_message}

I need you to help me complete this task step by step. For each action, explain your reasoning first, then take the action.

Current page: {current_url}
"""
                }
            ]
        }
        
        # Add message to conversation
        self.conversation.append(new_message)
        
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
            
            print(f"Calling OpenAI CUA API with {len(self.conversation)} conversation items...")
            
            # API request with proper error handling
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"API Error: {error_text}")
                        return {"text": f"Error from OpenAI API: {error_text}"}
                    
                    # Get response and parse it
                    response_text = await response.text()
                    try:
                        result = json.loads(response_text)
                    except json.JSONDecodeError:
                        print(f"Failed to parse API response: {response_text[:200]}...")
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
                            print(f"API Reasoning: {reasoning_text}")
                        self.last_reasoning = reasoning_text
                    elif "explanation" in reasoning_obj:
                        reasoning_text = reasoning_obj["explanation"]
                        if self.print_steps:
                            print(f"API Reasoning: {reasoning_text}")
                        self.last_reasoning = reasoning_text
            
            response_items = result["output"]
            
            # Process each item in the response
            return await self.process_response_items(response_items)
            
        except Exception as e:
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
        
        print(f"Processing {len(items)} response items from CUA")
        
        # Check if items array is empty
        if not items:
            print("Warning: Empty response items from CUA API")
            return {
                "text": "The browser automation system didn't return any actions to execute. Please try again with more specific instructions.",
                "screenshot": await self.browser_instance.take_screenshot(),
                "actions_executed": 0
            }
        
        # Process all items in a loop until we've completed all necessary actions
        while continue_execution and iterations < max_iterations:
            iterations += 1
            print(f"Execution iteration {iterations}")
            
            # Process current batch of items
            for item in items:
                print(f"Processing CUA response item type: {item.get('type')}")
                
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
                                    print(f"Extracted reasoning: {reasoning_text[:100]}...")
                                    results.append(f"💡 Reasoning: {reasoning_text}")
                                
                                # Add the message text to results
                                final_text += message_text + "\n\n"
                                commentary.append(f"💬 {message_text[:100]}...")
                                print(f"CUA message: {message_text[:100]}...")
                                results.append(f"[AI] {message_text}")
                
                elif item.get("type") == "computer_call":
                    actions_executed += 1
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
                    print(f"Executing: {action_desc}")
                    
                    # If no reasoning is available, generate one 
                    if not hasattr(self, 'last_reasoning') or not self.last_reasoning:
                        self.last_reasoning = self.generate_action_reasoning(action_type, action)
                        print(f"Generated reasoning: {self.last_reasoning}")
                        results.append(f"💡 Generated reasoning: {self.last_reasoning}")
                    
                    # Show reasoning alongside action for better context
                    if self.last_reasoning:
                        results.append(f"💭 Action context: {self.last_reasoning}")
                    
                    # Execute the computer action
                    try:
                        result_text = await self.execute_computer_action(action)
                        results.append(f"✅ {action_desc} - {result_text}")
                    except Exception as e:
                        error_msg = f"Error in {action_type}: {str(e)}"
                        print(error_msg)
                        results.append(f"❌ {action_desc} - {error_msg}")
                        # On error, we'll stop and not continue
                        continue_execution = False
                        break
                    
                    # Preserve reasoning for next action if needed
                    self.last_reasoning = None
            
            # If we should continue executing more actions, call the API again with updated state
            if continue_execution and actions_executed > 0 and iterations < max_iterations:
                # Take a new screenshot and prepare for next iteration
                screenshot = await self.browser_instance.take_screenshot()
                current_url = await self.browser_instance.get_current_url()
                
                # Create a clean message to continue the task
                try:
                    print("Getting next actions from CUA API...")
                    # Reset conversation to just have system message and current screenshot
                    if self.conversation and self.conversation[0].get("role") == "system":
                        system_message = self.conversation[0]
                        self.conversation = [system_message]
                    else:
                        self.conversation = [
                            {
                                "role": "system", 
                                "content": "You control a Chrome browser and need to help users accomplish tasks. Take actions in sequence to complete the user's request."
                            }
                        ]
                        
                    # Create a continuation message
                    continuation_message = {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{screenshot}"
                            },
                            {
                                "type": "input_text",
                                "text": f"""
Please continue with the previous task. I've completed the previous step.

Current page: {current_url}
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
                            async with session.post(url, headers=headers, json=payload) as response:
                                if response.status != 200:
                                    error_text = await response.text()
                                    print(f"Continuation API Error: {error_text}")
                                    continue_execution = False
                                else:
                                    response_text = await response.text()
                                    result = json.loads(response_text)
                                    if "output" in result:
                                        # Update the items to process and continue the loop
                                        items = result["output"]
                                        print(f"Received {len(items)} new items to process")
                                    else:
                                        print("No output in continuation response")
                                        continue_execution = False
                        except Exception as e:
                            print(f"Error in continuation API call: {str(e)}")
                            continue_execution = False
                except Exception as e:
                    print(f"Error preparing continuation: {str(e)}")
                    continue_execution = False
            else:
                # No more actions to perform or hit max iterations
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
        print(f"Executing action: {action_type} with params: {action}")
        
        try:
            if action_type == "click":
                x = action.get("x", 0)
                y = action.get("y", 0)
                button = action.get("button", "left")
                
                if button == "back":
                    await self.browser_instance.page.go_back()
                    return "Went back to previous page"
                elif button == "forward":
                    await self.browser_instance.page.go_forward()
                    return "Went forward to next page"
                else:
                    button_mapping = {"left": "left", "right": "right", "middle": "middle"}
                    button_type = button_mapping.get(button, "left")
                    await self.browser_instance.page.mouse.click(x, y, button=button_type)
                    return f"Clicked at ({x}, {y}) with {button} button"
            
            elif action_type == "double_click":
                x = action.get("x", 0)
                y = action.get("y", 0)
                await self.browser_instance.page.mouse.dblclick(x, y)
                return f"Double-clicked at ({x}, {y})"
                
            elif action_type == "type":
                text = action.get("text", "")
                await self.browser_instance.page.keyboard.type(text)
                return f"Typed: {text}"
                
            elif action_type == "keypress":
                keys = action.get("keys", [])
                for key in keys:
                    await self.browser_instance.page.keyboard.press(key)
                return f"Pressed keys: {', '.join(keys)}"
                
            elif action_type == "goto":
                url = action.get("url", "")
                if not url:
                    return "No URL provided for goto action"
                
                if check_blocklisted_url(url):
                    return f"Access to {url} is blocked for safety reasons"
                
                await self.browser_instance.page.goto(url, wait_until='domcontentloaded')
                return f"Navigated to: {url}"
                
            elif action_type == "wait":
                ms = action.get("ms", 1000)
                await asyncio.sleep(ms / 1000)
                return f"Waited for {ms} ms"
                
            elif action_type == "scroll":
                x = action.get("x", 0)
                y = action.get("y", 0)
                scroll_x = action.get("scroll_x", 0)
                scroll_y = action.get("scroll_y", 0)
                await self.browser_instance.page.mouse.move(x, y)
                await self.browser_instance.page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")
                return f"Scrolled by ({scroll_x}, {scroll_y}) from position ({x}, {y})"
                
            elif action_type == "move":
                x = action.get("x", 0)
                y = action.get("y", 0)
                await self.browser_instance.page.mouse.move(x, y)
                return f"Moved mouse to ({x}, {y})"
                
            elif action_type == "drag":
                path = action.get("path", [])
                if not path:
                    return "No path provided for drag action"
                
                await self.browser_instance.page.mouse.move(path[0].get("x", 0), path[0].get("y", 0))
                await self.browser_instance.page.mouse.down()
                for point in path[1:]:
                    await self.browser_instance.page.mouse.move(point.get("x", 0), point.get("y", 0))
                await self.browser_instance.page.mouse.up()
                return f"Dragged from ({path[0].get('x', 0)}, {path[0].get('y', 0)}) to ({path[-1].get('x', 0)}, {path[-1].get('y', 0)})"
            
            elif action_type == "screenshot":
                # This isn't a real action, but we'll handle it gracefully
                return "Taking screenshot (handled automatically)"
                
            else:
                return f"Unknown action type: {action_type}"
                
        except Exception as e:
            error_msg = f"Error executing {action_type} action: {str(e)}"
            print(error_msg)
            return error_msg
        
    async def process_message(self, message: str) -> dict:
        """Process a user message and operate the browser accordingly."""
        # Take a screenshot of the current state
        screenshot = await self.browser_instance.take_screenshot()
        if not screenshot:
            return {"text": "Could not take screenshot. Is the browser initialized?"}
        
        # Get the current URL
        current_url = await self.browser_instance.get_current_url()
        
        # Reset conversation for each message to avoid multiple image issues with CUA API
        # Start with just the system message
        self.conversation = [
            {
                "role": "system", 
                "content": "You control a Chrome browser and need to help users accomplish tasks. Take actions in sequence to complete the user's request."
            }
        ]
        
        # Call the OpenAI Computer Use API with a timeout
        try:
            print(f"Calling Computer Use API to process: {message}")
            api_task = asyncio.create_task(
                self.call_computer_use_api(message, screenshot, current_url)
            )
            
            # Wait for API call with timeout (90 seconds)
            result = await asyncio.wait_for(api_task, timeout=90)
            print(f"API processing complete. Actions executed: {result.get('actions_executed', 0)}")
            return result
        except asyncio.TimeoutError:
            return {
                "text": "Operation timed out after 90 seconds. The request may have been too complex or the API is experiencing delays.",
                "screenshot": screenshot
            }
        except Exception as e:
            print(f"Error in process_message: {str(e)}")
            return {
                "text": f"Error processing the operation: {str(e)}",
                "screenshot": screenshot
            }
    
    async def close(self):
        """Close the browser operator."""
        await self.browser_instance.close()
        self.conversation = []