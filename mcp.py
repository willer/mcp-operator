#!/usr/bin/env python3

import os
import sys
import logging
import subprocess
from pathlib import Path
import importlib.util

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def is_package_installed(package_name):
    """Check if a package is installed."""
    return importlib.util.find_spec(package_name) is not None

def ensure_dependencies():
    """Ensure all required dependencies are installed."""
    required_packages = [
        "uvicorn",
        "fastapi",
        "aiohttp",
        "playwright",
        "pydantic"
    ]
    
    # Check if requirements.txt exists and use it if available
    req_file = Path(__file__).parent / "requirements.txt"
    
    if req_file.exists():
        logger.info("Installing dependencies from requirements.txt")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies from requirements.txt: {str(e)}")
            # Continue and try individual packages
    
    # Verify each package is installed
    missing_packages = []
    for package in required_packages:
        if not is_package_installed(package):
            missing_packages.append(package)
    
    if missing_packages:
        logger.info(f"Installing missing dependencies: {', '.join(missing_packages)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing_packages])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {str(e)}")
            sys.exit(1)
    
    # Install playwright browsers
    if is_package_installed("playwright"):
        try:
            logger.info("Installing Playwright browsers (Chromium)")
            subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Playwright browsers: {str(e)}")
            logger.warning("Browser automation may not work correctly")

def main():
    """Entry point for the MCP."""
    logger.info("Starting MCP Operator for Browser Automation")
    
    # Ensure we have all required dependencies
    ensure_dependencies()
    
    # Import the main module (after ensuring dependencies)
    try:
        # Add the current directory to path to ensure imports work
        sys.path.insert(0, str(Path(__file__).parent))
        
        from src.main import main as run_server
        logger.info("Dependencies installed successfully, starting server")
        run_server()
    except ImportError as e:
        logger.error(f"Failed to import server module: {str(e)}")
        logger.error(f"Current working directory: {os.getcwd()}")
        logger.error(f"Python path: {sys.path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error starting server: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()