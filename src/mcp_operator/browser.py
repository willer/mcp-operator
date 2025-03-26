#!/usr/bin/env python3
"""
Browser operator implementation for MCP
"""

import os
import sys
import json
import asyncio
import uuid
import base64
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import logging

# Set up logging (file only, no stdout to preserve MCP protocol)
log_dir = Path(os.environ.get("MCP_LOG_DIR", "logs"))
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"mcp_operator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        # No stream handler to avoid interfering with MCP JSON-RPC
    ]
)

logger = logging.getLogger("mcp-operator")

# Import CUA components
from mcp_operator.cua.agent import Agent
from mcp_operator.cua.computer import AsyncLocalPlaywrightComputer

class BrowserInstance:
    """Manages a single browser instance"""
    
    def __init__(self, project_name: str):
        """Initialize browser instance
        
        Args:
            project_name: Unique identifier for this browser instance
        """
        self.project_name = project_name
        self.headless = True  # Default to headless mode
        self.dimensions = (1280, 1024)  # Default browser dimensions
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self.playwright_context = None
        self.initialized = False
        logger.info(f"Browser instance created for project: {project_name}")
    
    async def initialize(self):
        """Initialize the browser using Playwright"""
        width, height = self.dimensions
        
        from playwright.async_api import async_playwright
        self.playwright_context = async_playwright()
        self.playwright = await self.playwright_context.__aenter__()
        
        # Configure browser launch options
        browser_options = {
            "headless": self.headless,
            "args": [
                f"--window-size={width},{height}",
                "--disable-extensions",
                "--disable-web-security",
                "--disable-infobars",
                "--disable-notifications"
            ]
        }
        
        logger.info(f"Launching browser with options: {browser_options}")
        self.browser = await self.playwright.chromium.launch(**browser_options)
        
        # Create a context with specified viewport dimensions
        self.context = await self.browser.new_context(
            viewport={"width": width, "height": height},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        
        # Set up the domain filter to protect against malicious websites
        async def handle_route(route, request):
            url = request.url
            hostname = urlparse(url).hostname
            
            # Block known harmful domains
            blocked_domains = ["evil.com", "malware.org", "phishing.com"]
            if hostname and any(hostname.endswith(domain) for domain in blocked_domains):
                logger.warning(f"Blocked access to harmful site: {url}")
                await route.abort()
            else:
                await route.continue_()
        
        await self.context.route("**/*", handle_route)
        
        # Create the page
        self.page = await self.context.new_page()
        await self.page.goto("about:blank")
        
        self.initialized = True
        logger.info(f"Browser initialized for project: {self.project_name}")
    
    async def close(self):
        """Close the browser and cleanup resources"""
        if self.page:
            try:
                await self.page.close()
            except Exception as e:
                logger.error(f"Error closing page: {e}")
        
        if self.context:
            try:
                await self.context.close()
            except Exception as e:
                logger.error(f"Error closing context: {e}")
        
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
        
        if self.playwright_context:
            try:
                await self.playwright_context.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error stopping playwright: {e}")
        
        self.page = None
        self.context = None
        self.browser = None
        self.playwright = None
        self.playwright_context = None
        self.initialized = False
        logger.info(f"Browser closed for project: {self.project_name}")

class Job:
    """Represents a browser operation job"""
    
    def __init__(self, job_id: str, project_name: str, operation: str, **kwargs):
        """Initialize a job
        
        Args:
            job_id: Unique identifier for this job
            project_name: The project this job belongs to
            operation: Type of operation (create, navigate, operate, close)
            **kwargs: Additional job parameters
        """
        self.job_id = job_id
        self.project_name = project_name
        self.operation = operation
        self.params = kwargs
        self.status = "pending"
        self.result = None
        self.error = None
        self.created_at = datetime.now().isoformat()
        self.completed_at = None
        
        logger.info(f"Job created: {job_id} - {operation} for project {project_name}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary representation
        
        Returns:
            Dict containing job details
        """
        return {
            "job_id": self.job_id,
            "project_name": self.project_name,
            "operation": self.operation,
            "params": self.params,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }
    
    def complete(self, result: Any = None):
        """Mark the job as completed with results
        
        Args:
            result: The result data from the operation
        """
        self.status = "completed"
        self.result = result
        self.completed_at = datetime.now().isoformat()
        logger.info(f"Job completed: {self.job_id}")
    
    def fail(self, error: str):
        """Mark the job as failed with error message
        
        Args:
            error: Error message describing the failure
        """
        self.status = "failed"
        self.error = error
        self.completed_at = datetime.now().isoformat()
        logger.error(f"Job failed: {self.job_id} - {error}")

class BrowserOperator:
    """Manages browser automation through MCP"""
    
    def __init__(self, project_name: Optional[str] = None):
        """Initialize the browser operator
        
        Args:
            project_name: Optional project name, will be auto-generated if not provided
        """
        self.project_name = project_name or f"browser-{uuid.uuid4().hex[:8]}"
        self.browser_instance = None
        self.agent = None
        self.jobs: Dict[str, Job] = {}
        self.allow_domains = [
            "about:blank", "google.com", "www.google.com", 
            "github.com", "www.github.com",
            "example.com", "www.example.com",
            "wikipedia.org", "www.wikipedia.org",
            "cnn.com", "www.cnn.com",
            "openai.com", "www.openai.com",
            "anthropic.com", "www.anthropic.com"
        ]
        logger.info(f"Browser operator initialized with project name: {self.project_name}")
    
    def _generate_job_id(self) -> str:
        """Generate a unique job ID
        
        Returns:
            Unique job ID string
        """
        return f"job-{uuid.uuid4().hex}"
    
    async def create_browser(self) -> Dict[str, Any]:
        """Create a new browser instance
        
        Returns:
            Dict with job information
        """
        job_id = self._generate_job_id()
        job = Job(job_id, self.project_name, "create")
        self.jobs[job_id] = job
        
        try:
            # Check if browser already exists
            if self.browser_instance:
                await self.close()
            
            # Create and initialize the browser
            self.browser_instance = BrowserInstance(self.project_name)
            await self.browser_instance.initialize()
            
            # Complete the job successfully
            job.complete({"project_name": self.project_name})
            
        except Exception as e:
            logger.exception("Error creating browser")
            job.fail(str(e))
        
        return {"job_id": job_id}
    
    async def navigate_browser(self, url: str) -> Dict[str, Any]:
        """Navigate the browser to a URL
        
        Args:
            url: URL to navigate to
            
        Returns:
            Dict with job information
        """
        job_id = self._generate_job_id()
        job = Job(job_id, self.project_name, "navigate", url=url)
        self.jobs[job_id] = job
        
        try:
            # Ensure browser is initialized
            if not self.browser_instance or not self.browser_instance.initialized:
                raise ValueError("Browser not initialized. Call create_browser first.")
            
            # Check URL safety
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname
            
            # Validate URL
            if not parsed_url.scheme or not hostname:
                raise ValueError(f"Invalid URL: {url}")
            
            # Check if domain is allowed
            is_allowed = any(hostname.endswith(domain) for domain in self.allow_domains)
            if not is_allowed:
                raise ValueError(f"Domain not allowed: {hostname}")
            
            # Navigate to URL
            logger.info(f"Navigating to URL: {url}")
            await self.browser_instance.page.goto(url, wait_until="domcontentloaded")
            
            # Take screenshot after navigation
            screenshot = await self.browser_instance.page.screenshot()
            screenshot_base64 = base64.b64encode(screenshot).decode("utf-8")
            
            # Complete the job successfully
            job.complete({
                "current_url": self.browser_instance.page.url,
                "screenshot": screenshot_base64
            })
            
        except Exception as e:
            logger.exception(f"Error navigating to {url}")
            job.fail(str(e))
        
        return {"job_id": job_id}
    
    async def operate_browser(self, instruction: str) -> Dict[str, Any]:
        """Operate the browser based on a natural language instruction
        
        Args:
            instruction: Natural language instruction to execute
            
        Returns:
            Dict with job information
        """
        job_id = self._generate_job_id()
        job = Job(job_id, self.project_name, "operate", instruction=instruction)
        self.jobs[job_id] = job
        
        try:
            # Ensure browser is initialized
            if not self.browser_instance or not self.browser_instance.initialized:
                raise ValueError("Browser not initialized. Call create_browser first.")
                
            # Process the instruction using CUA
            result = await self.process_message(instruction)
            
            # Complete the job successfully
            job.complete(result)
            
        except Exception as e:
            logger.exception(f"Error operating browser with instruction: {instruction}")
            job.fail(str(e))
        
        return {"job_id": job_id}
    
    async def process_message(self, instruction: str) -> Dict[str, Any]:
        """Process a natural language instruction using CUA
        
        Args:
            instruction: The instruction to process
            
        Returns:
            Dict with results of the operation
        """
        logger.info(f"Processing instruction: {instruction}")
        
        # Initialize CUA agent if not already done
        if not self.agent:
            # Create computer instance that will communicate with our browser
            logger.info(f"Creating computer instance with headless={self.browser_instance.headless}")
            computer = AsyncLocalPlaywrightComputer(
                headless=self.browser_instance.headless,
                width=self.browser_instance.dimensions[0],
                height=self.browser_instance.dimensions[1],
                allowed_domains=self.allow_domains
            )
            
            # Create the agent
            self.agent = Agent(
                model="computer-use-preview",  # Use the specialized computer use model
                computer=computer,
                allowed_domains=self.allow_domains
            )
            
            logger.info("CUA agent initialized")
        
        # Run the agent to perform the instruction
        try:
            logger.info("Running CUA agent")
            result = await self.agent.run(instruction, max_steps=20)
            logger.info(f"Agent completed with success={result.success}")
            
            # Take final screenshot
            screenshot = await self.browser_instance.page.screenshot()
            screenshot_base64 = base64.b64encode(screenshot).decode("utf-8")
            
            # Create GIF from screen captures if available
            gif_path = None
            if result.screen_captures and len(result.screen_captures) > 0:
                try:
                    gif_dir = Path("./screenshots")
                    gif_dir.mkdir(exist_ok=True)
                    gif_path = str(gif_dir / f"{self.project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif")
                    self.agent.create_gif(gif_path)
                except Exception as e:
                    logger.error(f"Error creating GIF: {e}")
            
            # Get current URL
            current_url = self.browser_instance.page.url
            
            # Get console logs
            console_logs = await self.get_console_logs()
            
            # Return results
            return {
                "success": result.success,
                "text": result.message,
                "screenshot": screenshot_base64,
                "current_url": current_url,
                "console_logs": console_logs,
                "gif_path": gif_path,
                "actions_executed": len(result.screen_captures) if hasattr(result, "screen_captures") else 0
            }
            
        except Exception as e:
            logger.exception("Error in CUA agent execution")
            raise
    
    async def close(self) -> Dict[str, Any]:
        """Close the browser instance
        
        Returns:
            Dict with job information
        """
        job_id = self._generate_job_id()
        job = Job(job_id, self.project_name, "close")
        self.jobs[job_id] = job
        
        try:
            if self.browser_instance:
                await self.browser_instance.close()
                self.browser_instance = None
            
            # Reset agent
            self.agent = None
            
            # Complete the job successfully
            job.complete({"project_name": self.project_name, "status": "closed"})
            
        except Exception as e:
            logger.exception("Error closing browser")
            job.fail(str(e))
        
        return {"job_id": job_id}
    
    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get the status of a job
        
        Args:
            job_id: ID of the job to check
            
        Returns:
            Dict with job status information
        """
        if job_id not in self.jobs:
            return {"error": f"Job not found: {job_id}"}
        
        return self.jobs[job_id].to_dict()
    
    def list_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """List recent jobs
        
        Args:
            limit: Maximum number of jobs to return
            
        Returns:
            List of job dictionaries
        """
        # Sort jobs by creation time (newest first) and limit
        sorted_jobs = sorted(
            self.jobs.values(),
            key=lambda job: job.created_at,
            reverse=True
        )[:limit]
        
        return [job.to_dict() for job in sorted_jobs]
    
    async def add_note(self, name: str, content: str) -> Dict[str, Any]:
        """Add a user note
        
        Args:
            name: Name/title of the note
            content: Content of the note
            
        Returns:
            Dict with job information
        """
        job_id = self._generate_job_id()
        job = Job(job_id, self.project_name, "add_note", name=name, content=content)
        self.jobs[job_id] = job
        
        try:
            # Save note to file
            notes_dir = Path("./notes")
            notes_dir.mkdir(exist_ok=True)
            
            note_file = notes_dir / f"{self.project_name}_{name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            with open(note_file, "w") as f:
                f.write(f"Title: {name}\n")
                f.write(f"Date: {datetime.now().isoformat()}\n")
                f.write(f"Project: {self.project_name}\n")
                f.write("-" * 40 + "\n")
                f.write(content)
            
            # Complete the job successfully
            job.complete({"note_file": str(note_file)})
            
        except Exception as e:
            logger.exception(f"Error adding note: {name}")
            job.fail(str(e))
        
        return {"job_id": job_id}
    
    # Browser debugging tools
    
    async def get_console_logs(self) -> List[Dict[str, Any]]:
        """Get browser console logs
        
        Returns:
            List of console log entries
        """
        if not self.browser_instance or not self.browser_instance.initialized:
            return [{"error": "Browser not initialized"}]
        
        # Create a list to store logs
        logs = []
        
        # Set up a listener to capture logs if not already set up
        try:
            # Using playwright's console API
            page = self.browser_instance.page
            
            # Collect logs using evaluate
            result = await page.evaluate("""
            () => {
                return window.console_logs || [];
            }
            """)
            
            if result:
                logs.extend(result)
            
            return logs
        except Exception as e:
            logger.exception("Error getting console logs")
            return [{"error": str(e)}]
    
    async def get_console_errors(self) -> List[Dict[str, Any]]:
        """Get browser console errors
        
        Returns:
            List of console error entries
        """
        # Get all logs and filter for errors
        logs = await self.get_console_logs()
        
        # Filter for error logs only
        return [log for log in logs if log.get("type") == "error"]
    
    async def get_network_logs(self) -> List[Dict[str, Any]]:
        """Get browser network logs
        
        Returns:
            List of network log entries
        """
        if not self.browser_instance or not self.browser_instance.initialized:
            return [{"error": "Browser not initialized"}]
        
        try:
            # Using playwright to get network logs
            page = self.browser_instance.page
            
            # Collect network logs using evaluate
            result = await page.evaluate("""
            () => {
                return window.network_logs || [];
            }
            """)
            
            if result:
                return result
            return []
        except Exception as e:
            logger.exception("Error getting network logs")
            return [{"error": str(e)}]
    
    async def get_network_errors(self) -> List[Dict[str, Any]]:
        """Get browser network errors
        
        Returns:
            List of network error entries
        """
        # Get all network logs and filter for errors
        logs = await self.get_network_logs()
        
        # Filter for error logs only
        return [log for log in logs if log.get("status") >= 400]
    
    async def take_screenshot(self) -> Dict[str, Any]:
        """Take a screenshot of the current page
        
        Returns:
            Dict with screenshot data
        """
        if not self.browser_instance or not self.browser_instance.initialized:
            return {"error": "Browser not initialized"}
        
        try:
            # Take screenshot
            screenshot = await self.browser_instance.page.screenshot()
            screenshot_base64 = base64.b64encode(screenshot).decode("utf-8")
            
            return {"screenshot": screenshot_base64}
        except Exception as e:
            logger.exception("Error taking screenshot")
            return {"error": str(e)}
    
    async def get_selected_element(self) -> Dict[str, Any]:
        """Get information about the currently selected element
        
        Returns:
            Dict with element information
        """
        if not self.browser_instance or not self.browser_instance.initialized:
            return {"error": "Browser not initialized"}
        
        try:
            # Using playwright to get selected element
            page = self.browser_instance.page
            
            # Get information about currently focused element
            element_info = await page.evaluate("""
            () => {
                const activeElement = document.activeElement;
                if (!activeElement || activeElement === document.body) {
                    return { found: false };
                }
                
                const rect = activeElement.getBoundingClientRect();
                return {
                    found: true,
                    tag: activeElement.tagName.toLowerCase(),
                    id: activeElement.id,
                    className: activeElement.className,
                    text: activeElement.textContent?.trim().substring(0, 100) || "",
                    attributes: Array.from(activeElement.attributes).map(attr => ({ 
                        name: attr.name, 
                        value: attr.value 
                    })),
                    position: {
                        x: rect.left,
                        y: rect.top,
                        width: rect.width,
                        height: rect.height
                    }
                };
            }
            """)
            
            return element_info
        except Exception as e:
            logger.exception("Error getting selected element")
            return {"error": str(e)}
    
    async def wipe_logs(self) -> Dict[str, str]:
        """Wipe browser logs from memory
        
        Returns:
            Dict with status message
        """
        if not self.browser_instance or not self.browser_instance.initialized:
            return {"error": "Browser not initialized"}
        
        try:
            # Clear logs using evaluate
            await self.browser_instance.page.evaluate("""
            () => {
                window.console_logs = [];
                window.network_logs = [];
                console.log("Logs wiped");
            }
            """)
            
            return {"status": "Logs wiped successfully"}
        except Exception as e:
            logger.exception("Error wiping logs")
            return {"error": str(e)}
    
    # Audit tools
    
    async def _run_audit(self, audit_type: str) -> Dict[str, Any]:
        """Run a generic audit on the current page
        
        Args:
            audit_type: Type of audit to run
            
        Returns:
            Dict with audit results
        """
        if not self.browser_instance or not self.browser_instance.initialized:
            return {"error": "Browser not initialized"}
        
        try:
            # Using a simplified audit mechanism
            page = self.browser_instance.page
            
            # Run appropriate audit based on type
            audit_script = f"""
            () => {{
                // Simple audit implementation
                const results = {{}};
                
                // Common function to check meta tags
                const checkMetaTags = () => {{
                    const metas = document.querySelectorAll('meta');
                    const metaInfo = Array.from(metas).map(meta => {{
                        return {{
                            name: meta.getAttribute('name'),
                            property: meta.getAttribute('property'),
                            content: meta.getAttribute('content')
                        }};
                    }});
                    return metaInfo;
                }};
                
                // Check basic page metrics
                const getBasicMetrics = () => {{
                    return {{
                        title: document.title,
                        url: window.location.href,
                        loadTime: performance.now(),
                        docType: document.doctype ? document.doctype.name : 'unknown',
                        elementsCount: document.getElementsByTagName('*').length
                    }};
                }};
                
                results.basicMetrics = getBasicMetrics();
                
                // Specific audit logic based on type
                if ('{audit_type}' === 'accessibility') {{
                    // Basic accessibility checks
                    const imgWithoutAlt = document.querySelectorAll('img:not([alt])').length;
                    const formsWithoutLabels = document.querySelectorAll('input:not([id])').length;
                    const headingLevelsSkipped = (function() {{
                        const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
                        const levels = new Set();
                        for (const heading of headings) {{
                            levels.add(parseInt(heading.tagName[1]));
                        }}
                        const ordered = Array.from(levels).sort();
                        let skipped = false;
                        for (let i = 1; i < ordered.length; i++) {{
                            if (ordered[i] - ordered[i-1] > 1) {{
                                skipped = true;
                                break;
                            }}
                        }}
                        return skipped;
                    }})();
                    
                    results.accessibility = {{
                        imgWithoutAlt,
                        formsWithoutLabels,
                        headingLevelsSkipped,
                        ariaUsage: document.querySelectorAll('[aria-*]').length,
                        colorContrast: 'Manual check required'
                    }};
                }}
                
                if ('{audit_type}' === 'performance') {{
                    // Basic performance metrics
                    const perfEntries = performance.getEntriesByType('navigation');
                    results.performance = perfEntries.length > 0 ? perfEntries[0] : {{
                        loadTime: performance.now(),
                        resourceCount: performance.getEntriesByType('resource').length,
                        scriptCount: document.querySelectorAll('script').length,
                        stylesheetCount: document.querySelectorAll('link[rel="stylesheet"]').length,
                        imageCount: document.querySelectorAll('img').length,
                        totalBytes: 'Cannot calculate without browser API'
                    }};
                }}
                
                if ('{audit_type}' === 'seo') {{
                    // Basic SEO checks
                    results.seo = {{
                        metaTags: checkMetaTags(),
                        headings: {{
                            h1: document.querySelectorAll('h1').length,
                            h2: document.querySelectorAll('h2').length,
                            h3: document.querySelectorAll('h3').length
                        }},
                        imgWithAlt: document.querySelectorAll('img[alt]').length,
                        links: document.querySelectorAll('a').length,
                        canonicalLink: document.querySelector('link[rel="canonical"]')?.href
                    }};
                }}
                
                if ('{audit_type}' === 'nextjs') {{
                    // Check for NextJS specific patterns
                    const isNextJS = Boolean(
                        document.querySelector('#__next') || 
                        document.querySelector('script#__NEXT_DATA__')
                    );
                    
                    results.nextjs = {{
                        isNextJS,
                        nextRoot: Boolean(document.querySelector('#__next')),
                        nextData: Boolean(document.querySelector('script#__NEXT_DATA__')),
                        headManager: Boolean(document.querySelector('noscript#__next_css__DO_NOT_USE__'))
                    }};
                }}
                
                if ('{audit_type}' === 'bestPractices') {{
                    // Basic best practices checks
                    results.bestPractices = {{
                        docType: document.doctype !== null,
                        viewport: document.querySelector('meta[name="viewport"]') !== null,
                        charset: document.querySelector('meta[charset]') !== null,
                        consoleErrors: typeof window.console_logs === 'object' ? 
                            window.console_logs.filter(log => log.type === 'error').length : 'Console logs not captured',
                        deprecatedHtml: document.querySelectorAll('center, font, frame, frameset, marquee').length,
                        inlineStyles: document.querySelectorAll('[style]').length,
                        inlineJS: document.querySelectorAll('*[onclick], *[onload], *[onsubmit]').length
                    }};
                }}
                
                if ('{audit_type}' === 'debugger') {{
                    // Collect debug information
                    results.debugInfo = {{
                        dom: {{
                            bodyClasses: document.body.className,
                            bodyId: document.body.id,
                            elementCount: document.getElementsByTagName('*').length,
                            scripts: Array.from(document.scripts).map(s => s.src).filter(Boolean),
                            stylesheets: Array.from(document.styleSheets).length,
                            iframes: document.querySelectorAll('iframe').length
                        }},
                        environment: {{
                            userAgent: navigator.userAgent,
                            language: navigator.language,
                            screenSize: `${{window.innerWidth}}x${{window.innerHeight}}`,
                            devicePixelRatio: window.devicePixelRatio,
                            urlParams: Object.fromEntries(new URLSearchParams(window.location.search))
                        }}
                    }};
                }}
                
                if ('{audit_type}' === 'audit') {{
                    // Run all audits
                    // Accessibility
                    const imgWithoutAlt = document.querySelectorAll('img:not([alt])').length;
                    const formsWithoutLabels = document.querySelectorAll('input:not([id])').length;
                    
                    results.accessibility = {{
                        imgWithoutAlt,
                        formsWithoutLabels,
                        ariaUsage: document.querySelectorAll('[aria-*]').length
                    }};
                    
                    // Performance
                    const perfEntries = performance.getEntriesByType('navigation');
                    results.performance = perfEntries.length > 0 ? perfEntries[0] : {{
                        loadTime: performance.now(),
                        resourceCount: performance.getEntriesByType('resource').length
                    }};
                    
                    // SEO
                    results.seo = {{
                        metaTags: checkMetaTags(),
                        headings: {{
                            h1: document.querySelectorAll('h1').length,
                            h2: document.querySelectorAll('h2').length,
                            h3: document.querySelectorAll('h3').length
                        }}
                    }};
                    
                    // Best Practices
                    results.bestPractices = {{
                        docType: document.doctype !== null,
                        viewport: document.querySelector('meta[name="viewport"]') !== null,
                        charset: document.querySelector('meta[charset]') !== null
                    }};
                }}
                
                return results;
            }}
            """
            
            # Execute the audit script
            audit_results = await page.evaluate(audit_script)
            
            # Add timestamp
            audit_results["timestamp"] = datetime.now().isoformat()
            audit_results["url"] = page.url
            
            return audit_results
        except Exception as e:
            logger.exception(f"Error running {audit_type} audit")
            return {"error": str(e)}
    
    async def run_accessibility_audit(self) -> Dict[str, Any]:
        """Run an accessibility audit on the current page
        
        Returns:
            Dict with accessibility audit results
        """
        return await self._run_audit("accessibility")
    
    async def run_performance_audit(self) -> Dict[str, Any]:
        """Run a performance audit on the current page
        
        Returns:
            Dict with performance audit results
        """
        return await self._run_audit("performance")
    
    async def run_seo_audit(self) -> Dict[str, Any]:
        """Run an SEO audit on the current page
        
        Returns:
            Dict with SEO audit results
        """
        return await self._run_audit("seo")
    
    async def run_nextjs_audit(self) -> Dict[str, Any]:
        """Run a NextJS-specific audit on the current page
        
        Returns:
            Dict with NextJS audit results
        """
        return await self._run_audit("nextjs")
    
    async def run_best_practices_audit(self) -> Dict[str, Any]:
        """Run a best practices audit on the current page
        
        Returns:
            Dict with best practices audit results
        """
        return await self._run_audit("bestPractices")
    
    async def run_debugger_mode(self) -> Dict[str, Any]:
        """Run debugger mode to collect diagnostic information
        
        Returns:
            Dict with debug information
        """
        return await self._run_audit("debugger")
    
    async def run_audit_mode(self) -> Dict[str, Any]:
        """Run comprehensive audit mode
        
        Returns:
            Dict with comprehensive audit results
        """
        return await self._run_audit("audit")