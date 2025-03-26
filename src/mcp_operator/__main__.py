#!/usr/bin/env python3
"""
Main entry point for MCP Operator server
"""

import asyncio
import argparse
from mcp_operator.server import main as server_main

def main():
    """Parse arguments and run the MCP server"""
    parser = argparse.ArgumentParser(description="MCP Operator Server")
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Run the server
    asyncio.run(server_main())

if __name__ == "__main__":
    main()