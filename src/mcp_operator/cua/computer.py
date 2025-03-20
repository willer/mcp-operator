#!/usr/bin/env python3
"""
Computer implementations for the OpenAI Computer Use Agent (CUA)
"""
import asyncio
import base64
from typing import List, Dict, Tuple, Literal, Protocol, Any
from urllib.parse import urlparse

# Computer Protocol that defines the required methods for our CUA computer
class AsyncComputer(Protocol):
    """Defines the methods and properties required for our CUA computer"""
    
    @property
    def environment(self) -> Literal["browser"]: ...
    
    @property
    def dimensions(self) -> Tuple[int, int]: ...
    
    async def screenshot(self) -> str: ...
    
    async def click(self, x: int, y: int, button: str = "left") -> None: ...
    
    async def double_click(self, x: int, y: int) -> None: ...
    
    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None: ...
    
    async def type(self, text: str) -> None: ...
    
    async def wait(self, ms: int = 1000) -> None: ...
    
    async def move(self, x: int, y: int) -> None: ...
    
    async def keypress(self, keys: List[str]) -> None: ...
    
    async def drag(self, path: List[Dict[str, int]]) -> None: ...
    
    async def get_current_url(self) -> str: ...
    
    async def goto(self, url: str) -> None: ...

class AsyncPlaywrightComputer:
    """Base implementation for Playwright-based browser automation using the Async API"""
    
    environment: Literal["browser"] = "browser"
    dimensions = (1280, 1024)  # Default dimensions for the browser
    
    def __init__(self, allowed_domains=None):
        self._playwright = None
        self._browser = None
        self._page = None
        self.allowed_domains = allowed_domains or ['about:blank']
        
    async def __aenter__(self):
        from playwright.async_api import async_playwright
        # Start Playwright
        self._playwright = await async_playwright().start()
        self._browser, self._page = await self._get_browser_and_page()
        
        # Set up domain blocking based on allowed domains
        async def handle_route(route, request):
            url = request.url
            hostname = urlparse(url).hostname or ""
            
            # For important resources like stylesheets, scripts, fonts, and images, be more permissive
            resource_type = request.resource_type
            essential_resources = ["stylesheet", "script", "font", "image", "fetch", "xhr", "other"]
            
            # Check if it's allowed based on our domain list
            is_allowed = any(hostname.endswith(domain) for domain in self.allowed_domains)
            
            # Additional check for essential resources from CDNs
            cdn_domains = ["cdn", "jsdelivr", "cloudflare", "unpkg", "googleapis", "fontawesome"]
            is_cdn = any(cdn in hostname for cdn in cdn_domains)
            
            # Allow essential resources from known CDNs even if not explicitly in our domain list
            if resource_type in essential_resources and is_cdn:
                is_allowed = True
                
            # Special case for assets in the main application domain
            try:
                main_domain = urlparse(self._page.url).hostname
                if main_domain and hostname and hostname.endswith(main_domain):
                    is_allowed = True
            except:
                # If we can't get the current URL, be more lenient
                pass
                
            if not is_allowed:
                # Only log and block non-essential resources to reduce noise
                if resource_type not in ["image", "stylesheet", "font"]:
                    print(f"Blocking disallowed domain: {url}")
                await route.abort()
            else:
                await route.continue_()
                
        await self._page.route("**/*", handle_route)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
            
    async def screenshot(self) -> str:
        """Capture a screenshot of the current page"""
        # Export as PNG
        png_bytes = await self._page.screenshot(full_page=False)
        # Convert to base64 for API
        return base64.b64encode(png_bytes).decode("utf-8")
        
    async def click(self, x: int, y: int, button: str = "left") -> None:
        """Click at the specified coordinates"""
        if button == "back":
            await self.back()
        elif button == "forward":
            await self.forward()
        elif button == "wheel":
            await self._page.mouse.wheel(x, y)
        else:
            button_mapping = {"left": "left", "right": "right", "middle": "middle"}
            button_type = button_mapping.get(button, "left")
            await self._page.mouse.click(x, y, button=button_type)
            
    async def double_click(self, x: int, y: int) -> None:
        """Double-click at the specified coordinates"""
        await self._page.mouse.dblclick(x, y)
        
    async def scroll(self, x: int, y: int, scroll_x: int, scroll_y: int) -> None:
        """Scroll from a position"""
        await self._page.mouse.move(x, y)
        await self._page.evaluate(f"window.scrollBy({scroll_x}, {scroll_y})")
        
    async def type(self, text: str) -> None:
        """Type text with the keyboard"""
        await self._page.keyboard.type(text)
        
    async def wait(self, ms: int = 1000) -> None:
        """Wait for a specified time in milliseconds"""
        await asyncio.sleep(ms / 1000)
        
    async def move(self, x: int, y: int) -> None:
        """Move the mouse to the specified coordinates"""
        await self._page.mouse.move(x, y)
        
    async def keypress(self, keys: List[str]) -> None:
        """Press keyboard keys"""
        # Map common key names to Playwright key names
        key_mapping = {
            "CTRL": "Control",
            "CMD": "Meta",
            "ESC": "Escape",
            "ALT": "Alt",
            "SHIFT": "Shift",
            "TAB": "Tab",
            "ENTER": "Enter",
            "BACKSPACE": "Backspace",
            "DELETE": "Delete",
            "HOME": "Home",
            "END": "End",
            "PAGEUP": "PageUp",
            "PAGEDOWN": "PageDown",
            "ARROWUP": "ArrowUp",
            "ARROWDOWN": "ArrowDown",
            "ARROWLEFT": "ArrowLeft",
            "ARROWRIGHT": "ArrowRight",
            "SPACE": " "
        }
        
        for key in keys:
            # Convert key to lowercase for case-insensitive comparison
            key_lower = key.lower()
            # Use the mapping if available
            mapped_key = key_mapping.get(key.upper(), key)
            await self._page.keyboard.press(mapped_key)
            
    async def drag(self, path: List[Dict[str, int]]) -> None:
        """Perform a drag operation along a path"""
        if not path:
            return
        await self._page.mouse.move(path[0]["x"], path[0]["y"])
        await self._page.mouse.down()
        for point in path[1:]:
            await self._page.mouse.move(point["x"], point["y"])
        await self._page.mouse.up()
        
    async def get_current_url(self) -> str:
        """Get the current page URL"""
        return self._page.url
        
    async def goto(self, url: str) -> None:
        """Navigate to a URL"""
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"Error navigating to {url}: {e}")
            
    async def back(self) -> None:
        """Go back in browser history"""
        await self._page.go_back()
        
    async def forward(self) -> None:
        """Go forward in browser history"""
        await self._page.go_forward()
        
    async def _get_browser_and_page(self):
        """Set up browser and page - must be implemented by child classes"""
        raise NotImplementedError("Child classes must implement this method")

class AsyncLocalPlaywrightComputer(AsyncPlaywrightComputer):
    """Implementation of a local Playwright browser using the Async API"""
    
    def __init__(self, headless: bool = True, width: int = 1280, height: int = 1024, allowed_domains=None):
        super().__init__(allowed_domains=allowed_domains)
        self.headless = headless
        self.dimensions = (width, height)
        
    async def _get_browser_and_page(self):
        """Create a local browser instance"""
        width, height = self.dimensions
        
        # Launch arguments
        launch_args = [
            f"--window-size={width},{height}",
            "--disable-extensions",
            "--disable-web-security",  # Allow cross-domain cookies
            "--allow-running-insecure-content",  # Allow mixed content
            "--ignore-certificate-errors",  # Ignore SSL errors
        ]
        
        # Launch the browser
        browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args
        )
        
        # Create a new browser context with more permissive settings
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            ignore_https_errors=True,  # Ignore HTTPS errors
            accept_downloads=True,  # Accept downloads
        )
        
        # Set up default permissions
        # Grant all permissions to make the browser work more like a human user's browser
        permissions = [
            'geolocation',
            'notifications',
            'camera',
            'microphone',
            'clipboard-read',
            'clipboard-write'
        ]
        await context.grant_permissions(permissions)
        
        # Create a page
        page = await context.new_page()
        
        # Load blank page initially
        await page.goto("about:blank")
        
        return browser, page