#!/usr/bin/env python3

import asyncio
import os
import sys
import logging
from pathlib import Path
from importlib import metadata

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

def ensure_dependencies():
    """Ensure all required dependencies are installed."""
    required_packages = [
        "uvicorn",
        "fastapi",
        "aiohttp",
        "playwright",
        "pydantic"
    ]
    
    missing_packages = []
    for package in required_packages:
        try:
            metadata.version(package)
        except metadata.PackageNotFoundError:
            missing_packages.append(package)
    
    if missing_packages:
        logger.info(f"Installing missing dependencies: {', '.join(missing_packages)}")
        try:
            import pip
            pip.main(["install", *missing_packages])
            
            # Special case for playwright - needs to install browsers
            if "playwright" in missing_packages:
                import subprocess
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        except Exception as e:
            logger.error(f"Failed to install dependencies: {str(e)}")
            sys.exit(1)

def main():
    """Entry point for the MCP."""
    # Ensure we have all required dependencies
    ensure_dependencies()
    
    # Import the main module (after ensuring dependencies)
    try:
        from src.main import main as run_server
        run_server()
    except ImportError as e:
        logger.error(f"Failed to import server module: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()