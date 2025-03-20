#!/usr/bin/env python3
"""
Browser implementation for the MCP Browser Operator

This module acts as an adapter between the CUA implementation and the MCP server,
allowing the CUA browser automation to be exposed as MCP tools.
"""
import urllib.parse

# Define blocklisted domains for security
BLOCKLISTED_DOMAINS = [
    'evil.com',
    'malware.com',
    'phishing.com',
    'dangerous.site',
    'sketchy.net'
]

def check_blocklisted_url(url):
    """Check if a URL is blocklisted for security
    
    Args:
        url: The URL to check
        
    Returns:
        bool: True if the URL is blocklisted, False otherwise
    """
    # Chrome error pages should be allowed
    if url.startswith("chrome-error://"):
        return False
        
    try:
        # Skip blocking for data URLs, about pages, and chrome special pages
        if url.startswith(("data:", "about:", "chrome:", "chrome-extension:")):
            return False
            
        # Parse the domain from the URL
        domain = urllib.parse.urlparse(url).netloc.lower()
        
        # Only block known harmful domains
        return any(blocked in domain for blocked in BLOCKLISTED_DOMAINS)
    except:
        # For any parsing error, allow by default (changed from blocking)
        return False
import asyncio
import base64
import logging
import os
import traceback
from typing import Dict, Any, Optional, List, Tuple

from playwright.async_api import async_playwright

from .cua.agent import Agent
from .cua.computer import AsyncLocalPlaywrightComputer

# Create our logger that only writes to file
logger = logging.getLogger('mcp-operator')

class BrowserInstance:
    """Wrapper around CUA's AsyncLocalPlaywrightComputer for MCP compatibility"""
    
    def __init__(self, browser_id: str, headless: bool = True, width: int = 1280, height: int = 1024):
        """Initialize a browser instance
        
        Args:
            browser_id: Unique identifier for this browser
            headless: Whether to run in headless mode
            width: Browser window width
            height: Browser window height
        """
        self.browser_id = browser_id
        self.headless = headless
        self.width = width
        self.height = height
        self.dimensions = (width, height)
        
        # These will be set during initialization
        self.computer = None
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        
        # Use a blocklist approach - only block known harmful sites
        # These are the domains we'll never allow navigation to
        self.blocked_domains = [
            'evil.com', 'malware.com', 'phishing.com', 'dangerous.site', 
            'sketchy.net', 'malicious.org', 'virus.com', 'spyware.net'
        ]
        
        # For backward compatibility, maintain an allowed_domains attribute 
        # but make it very permissive (effectively everything except the blocklist)
        self.allowed_domains = ['*']
        
        logger.info(f"Created browser instance with ID: {browser_id}, dimensions: {width}x{height}")
        
    async def initialize(self):
        """Initialize the browser and page"""
        try:
            # Create the AsyncLocalPlaywrightComputer instance
            self.computer = AsyncLocalPlaywrightComputer(
                headless=self.headless,
                width=self.width,
                height=self.height,
                allowed_domains=self.allowed_domains
            )
            
            # Enter the context (this initializes Playwright, browser, context, and page)
            await self.computer.__aenter__()
            
            # Store references to the components for easier access
            self.page = self.computer._page
            self.context = self.computer._browser.contexts[0]
            self.browser = self.computer._browser
            self.playwright = self.computer._playwright
            
            # Set viewport size
            await self.page.set_viewport_size({"width": self.width, "height": self.height})
            
            # Navigate to Google as a default starting page
            await self.page.goto("https://google.com", wait_until="domcontentloaded", timeout=30000)
            
            logger.info(f"Browser instance {self.browser_id} initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Error initializing browser instance {self.browser_id}: {str(e)}")
            logger.error(traceback.format_exc())
            return False
            
    async def take_screenshot(self) -> str:
        """Take a screenshot of the current page
        
        Returns:
            Base64-encoded screenshot
        """
        try:
            return await self.computer.screenshot()
        except Exception as e:
            logger.error(f"Error taking screenshot: {str(e)}")
            return ""
            
    async def close(self):
        """Close the browser and clean up resources"""
        try:
            if self.computer:
                await self.computer.__aexit__(None, None, None)
                
            # Clear references
            self.computer = None
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            
            logger.info(f"Browser instance {self.browser_id} closed successfully")
        except Exception as e:
            logger.error(f"Error closing browser instance {self.browser_id}: {str(e)}")
            logger.error(traceback.format_exc())

class BrowserOperator:
    """Manages browser operations and interaction with the OpenAI Computer Use API"""
    
    def __init__(self, project_name: str):
        """Initialize a browser operator
        
        Args:
            project_name: Project identifier for this browser instance
        """
        self.project_name = project_name
        self.browser_instance = BrowserInstance(project_name)
        self.agent = None
        
        logger.info(f"Created browser operator for project: {project_name}")
        
    async def initialize(self):
        """Initialize the browser instance"""
        success = await self.browser_instance.initialize()
        if success:
            # Create the CUA Agent 
            if hasattr(self.browser_instance, 'computer') and self.browser_instance.computer:
                self.agent = Agent(
                    computer=self.browser_instance.computer,
                    allowed_domains=self.browser_instance.allowed_domains
                )
                logger.info(f"Browser operator for project {self.project_name} initialized")
            else:
                # In the test case where a custom patched_init is used, the computer object might not be created
                # We need to adapt to those specialized patched initialization methods
                logger.warning(f"Using custom browser instance setup without CUA computer for project {self.project_name}")
                from .cua.computer import AsyncLocalPlaywrightComputer
                
                # Create a computer adapter that can work with a directly initialized page
                computer = AsyncLocalPlaywrightComputer(
                    headless=self.browser_instance.headless,
                    width=self.browser_instance.width, 
                    height=self.browser_instance.height,
                    allowed_domains=self.browser_instance.allowed_domains
                )
                
                # Set up the browser components directly
                computer._browser = self.browser_instance.browser
                computer._page = self.browser_instance.page
                self.browser_instance.computer = computer
                
                # Create the agent
                self.agent = Agent(
                    computer=computer,
                    allowed_domains=self.browser_instance.allowed_domains
                )
                logger.info(f"Browser operator with custom setup for project {self.project_name} initialized")
                
        return success
        
    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL
        
        Args:
            url: The URL to navigate to
            
        Returns:
            Dict with results of the navigation
        """
        try:
            # Ensure URL has a protocol
            if not url.startswith("http"):
                url = f"https://{url}"
                
            logger.info(f"Navigating to {url}")
            
            # Use the agent to navigate to the URL
            instruction = f"Please navigate to {url}"
            result = await self.process_message(instruction)
            
            return {
                "text": f"Navigated to {url}",
                "screenshot": result.get("screenshot", ""),
                "url": url
            }
        except Exception as e:
            logger.error(f"Error navigating to {url}: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "text": f"Error navigating to {url}: {str(e)}",
                "screenshot": await self.browser_instance.take_screenshot(),
                "url": url,
                "error": str(e)
            }
            
    async def process_message(self, instruction: str) -> Dict[str, Any]:
        """Process a user instruction through the Computer Use API
        
        Args:
            instruction: The user's instruction for the browser
            
        Returns:
            Dict with results of the instruction processing
        """
        try:
            logger.info(f"Processing instruction: {instruction}")
            
            # Call the agent with the instruction and handle API errors
            try:
                result = await self.agent.run(instruction)
                
                # Create a response with the combined information
                message = result.message if hasattr(result, 'message') else "Task completed"
                success = result.success if hasattr(result, 'success') else False
                
                # Extract actions executed from conversation history
                actions_executed = 0
                if hasattr(self.agent, 'conversation_history'):
                    for item in self.agent.conversation_history:
                        if item.get('type') == 'action':
                            actions_executed += 1
                
                logger.info(f"Instruction processed with {actions_executed} actions executed")
            except Exception as agent_error:
                logger.error(f"Agent run error: {str(agent_error)}")
                logger.error(traceback.format_exc())
                
                # Check for specific OpenAI API errors
                error_text = str(agent_error)
                if "server_error" in error_text or "500" in error_text:
                    message = "Task failed: OpenAI Computer Use API is experiencing server errors. Please try again later."
                elif "rate limit" in error_text.lower():
                    message = "Task failed: OpenAI API rate limit exceeded. Please try again in a few minutes."
                elif "quota" in error_text.lower():
                    message = "Task failed: OpenAI API quota exceeded. Please check your account billing and limits."
                elif any(term in error_text.lower() for term in ["authentication", "unauthorized", "auth", "key"]):
                    message = "Task failed: OpenAI API authentication error. Please check your API key."
                else:
                    # Generic error message
                    message = f"Task failed: {str(agent_error)}"
                
                success = False
                actions_executed = 0
            
            # Get the latest screenshot - do this outside the try/except so we get one even on error
            try:
                screenshot = await self.browser_instance.take_screenshot()
            except Exception as screenshot_error:
                logger.error(f"Screenshot error: {str(screenshot_error)}")
                screenshot = ""  # Empty string if screenshot fails
            
            response = {
                "text": message,
                "screenshot": screenshot,
                "success": success,
                "actions_executed": actions_executed
            }
            
            return response
        except Exception as e:
            logger.error(f"Error in process_message: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Try to get a screenshot even if there was an error
            try:
                screenshot = await self.browser_instance.take_screenshot()
            except Exception as screenshot_error:
                logger.error(f"Screenshot error during exception handling: {str(screenshot_error)}")
                screenshot = ""
                
            return {
                "text": f"Error processing instruction: {str(e)}",
                "screenshot": screenshot,
                "success": False,
                "actions_executed": 0,
                "error": str(e)
            }
            
    async def close(self):
        """Close the browser instance and clean up resources"""
        try:
            await self.browser_instance.close()
            logger.info(f"Browser operator for project {self.project_name} closed")
        except Exception as e:
            logger.error(f"Error closing browser operator: {str(e)}")
            logger.error(traceback.format_exc())