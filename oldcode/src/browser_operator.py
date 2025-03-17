#!/usr/bin/env python3

import asyncio
import base64
import json
import os
from typing import Dict, List, Optional, Any

import aiohttp
import playwright.async_api as pw
from playwright.async_api import Page, Browser, BrowserContext


class BrowserInstance:
    """A class to manage a browser instance."""
    
    def __init__(self, browser_id: str):
        self.browser_id = browser_id
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
    async def initialize(self):
        """Initialize the browser instance."""
        playwright = await pw.async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()
        
    async def navigate(self, url: str) -> str:
        """Navigate to a URL."""
        if not self.page:
            return "Browser not initialized"
        
        try:
            await self.page.goto(url)
            return f"Navigated to {url}"
        except Exception as e:
            return f"Error navigating to {url}: {str(e)}"
    
    async def take_screenshot(self) -> Optional[str]:
        """Take a screenshot of the current page."""
        if not self.page:
            return None
        
        try:
            screenshot_bytes = await self.page.screenshot()
            return base64.b64encode(screenshot_bytes).decode('utf-8')
        except Exception as e:
            return None
    
    async def get_page_content(self) -> str:
        """Get the content of the current page."""
        if not self.page:
            return "Browser not initialized"
        
        try:
            content = await self.page.content()
            return content
        except Exception as e:
            return f"Error getting page content: {str(e)}"
    
    async def execute_action(self, action: Dict[str, Any]) -> str:
        """Execute a browser action."""
        if not self.page:
            return "Browser not initialized"
        
        action_type = action.get("type")
        
        try:
            if action_type == "click":
                selector = action.get("selector")
                if selector:
                    await self.page.click(selector)
                    return f"Clicked on element with selector: {selector}"
                else:
                    return "No selector provided for click action"
                
            elif action_type == "type":
                selector = action.get("selector")
                text = action.get("text")
                if selector and text:
                    await self.page.fill(selector, text)
                    return f"Typed '{text}' into element with selector: {selector}"
                else:
                    return "Missing selector or text for type action"
                
            elif action_type == "navigate":
                url = action.get("url")
                if url:
                    return await self.navigate(url)
                else:
                    return "No URL provided for navigate action"
                
            elif action_type == "wait":
                selector = action.get("selector")
                timeout = action.get("timeout", 30000)
                if selector:
                    await self.page.wait_for_selector(selector, timeout=timeout)
                    return f"Waited for element with selector: {selector}"
                else:
                    time_ms = action.get("time", 1000)
                    await asyncio.sleep(time_ms / 1000)
                    return f"Waited for {time_ms} ms"
                
            else:
                return f"Unknown action type: {action_type}"
                
        except Exception as e:
            return f"Error executing {action_type} action: {str(e)}"
    
    async def close(self):
        """Close the browser instance."""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.context = None
            self.page = None


class BrowserOperator:
    """A class to operate a browser using the OpenAI computer-use-preview API."""
    
    def __init__(self, browser_id: str):
        self.browser_id = browser_id
        self.browser_instance = BrowserInstance(browser_id)
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        
    async def initialize(self):
        """Initialize the browser operator."""
        await self.browser_instance.initialize()
        
    async def process_message(self, message: str) -> str:
        """Process a user message and operate the browser accordingly."""
        # Take a screenshot of the current state
        screenshot = await self.browser_instance.take_screenshot()
        if not screenshot:
            return "Could not take screenshot. Is the browser initialized?"
        
        # Get the page content
        page_content = await self.browser_instance.get_page_content()
        
        # Prepare the payload for OpenAI's computer-use-preview API
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "system",
                    "content": """
                    You are a browser automation assistant. Given a screenshot of a web page and user instructions,
                    determine the actions to take to accomplish the user's request. Return a JSON array of actions.
                    Each action should have a 'type' field, which can be one of: 'click', 'type', 'navigate', 'wait'.
                    
                    For click actions, include a 'selector' field with a CSS selector.
                    For type actions, include 'selector' and 'text' fields.
                    For navigate actions, include a 'url' field.
                    For wait actions, include either a 'selector' field or a 'time' field in milliseconds.
                    
                    Example:
                    [
                        {"type": "navigate", "url": "https://example.com"},
                        {"type": "click", "selector": "#login-button"},
                        {"type": "type", "selector": "#username", "text": "user123"},
                        {"type": "wait", "selector": ".loading-indicator", "timeout": 5000}
                    ]
                    """
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"User request: {message}\n\nPlease determine the actions to take:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{screenshot}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 4096
        }
        
        # Call OpenAI's API
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.openai_api_key}"
                    },
                    json=payload
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        return f"Error from OpenAI API: {error_text}"
                    
                    result = await response.json()
                    actions_text = result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error calling OpenAI API: {str(e)}"
        
        # Parse the actions from the API response
        try:
            # Extract JSON from the response which might contain markdown code blocks
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', actions_text)
            if json_match:
                actions_json = json_match.group(1)
            else:
                actions_json = actions_text
            
            actions = json.loads(actions_json)
            
            # Execute each action
            results = []
            for action in actions:
                result = await self.browser_instance.execute_action(action)
                results.append(result)
            
            # Take a new screenshot after actions
            new_screenshot = await self.browser_instance.take_screenshot()
            
            return "\n".join([
                "Actions executed:",
                *[f"- {result}" for result in results],
                "",
                "Current page state is attached as a screenshot."
            ])
            
        except json.JSONDecodeError:
            return f"Could not parse actions from OpenAI response: {actions_text}"
        except Exception as e:
            return f"Error executing actions: {str(e)}"
    
    async def close(self):
        """Close the browser operator."""
        await self.browser_instance.close()