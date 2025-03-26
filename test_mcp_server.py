#!/usr/bin/env python3
"""
Test script for the MCP Browser Operator server
This script sends a series of test requests to verify core functionality.
"""

import json
import sys
import time
import asyncio
import subprocess
from pathlib import Path

async def send_request(process, request_data):
    """Send a JSON-RPC request to the MCP server process"""
    request_json = json.dumps(request_data)
    print(f"\n>>> Sending: {request_json}")
    process.stdin.write(request_json + "\n")
    process.stdin.flush()
    
    # Read the response
    response_line = process.stdout.readline().strip()
    if not response_line:
        print("No response received!")
        return None
    
    try:
        response = json.loads(response_line)
        print(f"<<< Received: {json.dumps(response, indent=2)}")
        return response
    except json.JSONDecodeError:
        print(f"Error parsing response: {response_line}")
        return None

async def main():
    """Run the test sequence"""
    # Start the MCP server process
    cmd = [sys.executable, "run_mcp.py"]
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered
    )
    
    print(f"Started MCP server process (PID: {process.pid})")
    
    try:
        # Test 1: Create a browser
        create_response = await send_request(process, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "mcp__browser-operator__create-browser",
            "params": {
                "project_name": "test-project"
            }
        })
        
        if not create_response or "error" in create_response:
            print("Browser creation failed!")
            return
        
        job_id = create_response["result"]["job_id"]
        print(f"Browser creation job ID: {job_id}")
        
        # Test 2: Check job status until complete
        max_wait = 30  # seconds
        start_time = time.time()
        status = None
        
        while time.time() - start_time < max_wait:
            status_response = await send_request(process, {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "mcp__browser-operator__get-job-status",
                "params": {
                    "job_id": job_id
                }
            })
            
            if not status_response or "error" in status_response:
                print("Failed to get job status!")
                break
                
            status = status_response["result"]["status"]
            print(f"Job status: {status}")
            
            if status == "completed":
                break
                
            await asyncio.sleep(1)
        
        if status != "completed":
            print("Browser creation did not complete in time!")
            return
            
        print("Browser created successfully!")
        
        # Test 3: Navigate browser
        navigate_response = await send_request(process, {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "mcp__browser-operator__navigate-browser",
            "params": {
                "project_name": "test-project",
                "url": "https://example.com"
            }
        })
        
        if not navigate_response or "error" in navigate_response:
            print("Navigation failed!")
            return
            
        navigate_job_id = navigate_response["result"]["job_id"]
        print(f"Navigation job ID: {navigate_job_id}")
        
        # Test 4: Check navigation status until complete
        max_wait = 30  # seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_response = await send_request(process, {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "mcp__browser-operator__get-job-status",
                "params": {
                    "job_id": navigate_job_id
                }
            })
            
            if not status_response or "error" in status_response:
                print("Failed to get navigation job status!")
                break
                
            status = status_response["result"]["status"]
            print(f"Navigation job status: {status}")
            
            if status == "completed":
                # Print URL for confirmation
                url = status_response["result"]["result"]["current_url"]
                print(f"Navigation complete, current URL: {url}")
                break
                
            await asyncio.sleep(1)
        
        # Test 5: Take a screenshot
        screenshot_response = await send_request(process, {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "mcp__browser-tools__takeScreenshot",
            "params": {}
        })
        
        if not screenshot_response or "error" in screenshot_response:
            print("Screenshot failed!")
        else:
            # Save screenshot to file if successful
            if "screenshot" in screenshot_response["result"]:
                import base64
                screenshot_dir = Path("screenshots")
                screenshot_dir.mkdir(exist_ok=True)
                screenshot_path = screenshot_dir / f"test_screenshot_{int(time.time())}.png"
                
                with open(screenshot_path, "wb") as f:
                    f.write(base64.b64decode(screenshot_response["result"]["screenshot"]))
                    
                print(f"Screenshot saved to: {screenshot_path}")
        
        # Test 6: Close the browser
        close_response = await send_request(process, {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "mcp__browser-operator__close-browser",
            "params": {
                "project_name": "test-project"
            }
        })
        
        if not close_response or "error" in close_response:
            print("Browser close failed!")
            return
            
        close_job_id = close_response["result"]["job_id"]
        print(f"Close job ID: {close_job_id}")
        
        # Check close job status
        max_wait = 10  # seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_response = await send_request(process, {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "mcp__browser-operator__get-job-status",
                "params": {
                    "job_id": close_job_id
                }
            })
            
            if not status_response or "error" in status_response:
                print("Failed to get close job status!")
                break
                
            status = status_response["result"]["status"]
            print(f"Close job status: {status}")
            
            if status == "completed":
                print("Browser closed successfully!")
                break
                
            await asyncio.sleep(1)
        
        print("\nAll tests completed!")
        
    finally:
        # Clean up the process
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        
        # Get stderr output for debugging
        stderr = process.stderr.read()
        if stderr:
            print(f"\nServer stderr output:\n{stderr}")

if __name__ == "__main__":
    asyncio.run(main())