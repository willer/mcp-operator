#!/usr/bin/env python3
"""
Run the MCP Browser Operator server
"""

import os
import sys
import argparse
from pathlib import Path

# Ensure the src directory is in the path
src_dir = Path(__file__).parent / "src"
sys.path.insert(0, str(src_dir))

def main():
    """
    Parse command line arguments and run the MCP server
    """
    parser = argparse.ArgumentParser(description="MCP Browser Operator Server")
    parser.add_argument(
        "--log-dir", 
        type=str, 
        default="logs",
        help="Directory for server logs (default: logs)"
    )
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Set environment variables
    os.environ["MCP_LOG_DIR"] = args.log_dir
    if args.debug:
        os.environ["MCP_DEBUG"] = "1"
    
    # Import and run the server
    from mcp_operator.server import main as server_main
    import asyncio
    asyncio.run(server_main())

if __name__ == "__main__":
    main()