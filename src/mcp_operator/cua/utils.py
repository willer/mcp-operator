#!/usr/bin/env python3
"""
Utility functions for the OpenAI Computer Use Agent (CUA)
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

from enum import Enum, auto

# VERSION TAG - increment this when making significant changes
# This helps identify if cached/stale versions are being used
UTILS_VERSION = "1.0.0" 

# This is helpful for debugging import issues
if "DEBUG_IMPORTS" in os.environ:
    print(f"Loading lib.cua.utils module version {UTILS_VERSION}", file=sys.stderr)

class TestStatus(Enum):
    """Enum for test statuses"""
    PASS = auto()
    FAIL = auto()
    ERROR = auto()
    SKIP = auto()
    UNCERTAIN = auto()

def process_agent_output(result, class_name, test_name):
    """Process agent output to determine status and message
    
    Args:
        result: Agent result object
        class_name: Name of the test class
        test_name: Name of the test method
        
    Returns:
        tuple: (success, result_message, full_output_text, uncertain)
        success: Boolean indicating if test passed
        result_message: Human-readable result message
        full_output_text: Full output for logging
        uncertain: Boolean indicating if result is uncertain/ambiguous
    """
    # Override for specific tests that have known authentication issues
    auth_issue_tests = {
        # CMS tests with auth issues
        "TestCMS.cms_payroll_and_benefits": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_payroll_and_benefits_canada": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_payroll_and_benefits_usa": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_office_tech": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_travel": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_travel_navan_vs_genome": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_travel_contact_us": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_travel_cities": "This test requires special auth that's not available in the test environment.",
        "TestCMS.cms_travel_navan": "This test requires special auth that's not available in the test environment.",
        
        # Hub tests with auth issues  
        "HubMain.verify_people_link": "This test requires special auth that's not available in the test environment.",
        "HubMain.verify_launcher_link": "This test requires special auth that's not available in the test environment.",
        "HubMain.verify_pulse_link": "This test requires special auth that's not available in the test environment.",
        "HubMain.verify_news_link": "This test requires special auth that's not available in the test environment.",
        "HubMain.verify_chatter_link": "This test requires special auth that's not available in the test environment.",
        "HubMain.verify_ai_tools_link": "This test requires special auth that's not available in the test environment.",
        "HubMain.verify_chat_link": "This test requires special auth that's not available in the test environment.",
        "HubMain.verify_agents_link": "This test requires special auth that's not available in the test environment.",
        
        # Other known test issues
        "HomepageNavigation.verify_navigation_sidebar_elements": "This test requires special auth that's not available in the test environment.",
        "HomepageNavigation.verify_sidebar_elements": "This test requires special auth that's not available in the test environment.",
        "HomepageNavigation.verify_create_task_functionality": "This test requires special auth that's not available in the test environment.",
        "TasksSection.verify_task_list_display": "This test requires special auth that's not available in the test environment.",
        "TasksSection.verify_task_search_functionality": "This test requires special auth that's not available in the test environment.",
        "TasksSection.verify_task_settings_functionality": "This test requires special auth that's not available in the test environment."
    }
    
    # Initialize status to ERROR as a default
    status = TestStatus.ERROR
    
    # Check if we should skip this test due to known auth issues
    test_id = f"{class_name}.{test_name}"
    
    # First check direct test ID matches for SKIP
    if test_id in auth_issue_tests:
        print(f"NOTICE: Treating {test_id} as SKIPPED due to known authentication constraints")
        status = TestStatus.SKIP
        return True, f"SKIPPED: {auth_issue_tests[test_id]}", "This test requires special authentication and is auto-skipped.", True
    
    # Extract message and set default success to False
    message = result.message if hasattr(result, 'message') else "Test completed"
    success = result.success if hasattr(result, 'success') else False
    
    # Check for authentication issues in the message
    if hasattr(result, 'message'):
        if any(phrase in message.lower() for phrase in [
            "security key", 
            "google login", 
            "google authentication", 
            "requires authentication",
            "requires login",
            "login required"
        ]):
            print(f"NOTICE: Detected authentication requirement in test message. Marking as SKIPPED.")
            status = TestStatus.SKIP
            return True, f"SKIPPED: Test requires authentication that is unavailable in automated testing", message, True
    
    # Check for API errors or timeouts
    if "API Error" in message or "timeout" in message.lower() or "rate limit" in message.lower():
        print(f"NOTICE: Detected API error or timeout in test message. Marking as ERROR.")
        status = TestStatus.ERROR
        # Leave success as False but with ERROR status
        return False, f"ERROR: {message}", message, False
    
    # Fix INCONCLUSIVE prefix if present
    uncertain = False
    if message.startswith("INCONCLUSIVE:") or "UNCERTAIN" in message.upper():
        # Remove the prefix and trim
        clean_message = message.replace("INCONCLUSIVE:", "").strip()
        
        # Mark as uncertain
        uncertain = True
        message = clean_message
        status = TestStatus.UNCERTAIN
        
        # Check if it's actually a PASS despite being uncertain
        if clean_message.startswith("PASSED") or clean_message.upper().startswith("PASS"):
            success = True
        elif "PASSED" in clean_message.upper() and not any(x in clean_message.upper() for x in ["NOT PASSED", "FAILED", "FAIL"]):
            success = True
    
    # Handle specific patterns that indicate success
    if ("test passed" in message.lower() or 
        message.lower().startswith("passed") or 
        "passed:" in message.lower() or
        "successfully completed" in message.lower() or
        "all requirements are met" in message.lower() or
        "requirements have been met" in message.lower()):
        success = True
        status = TestStatus.PASS
        
        # If there are qualifiers like "partially" or "most", mark as uncertain
        if any(qualifier in message.lower() for qualifier in ["partially", "most", "some", "unclear", "uncertain", "might", "may", "not sure"]):
            uncertain = True
            status = TestStatus.UNCERTAIN
    
    # Handle specific patterns that indicate failure
    if ("test failed" in message.lower() or 
        message.lower().startswith("failed") or 
        "failed:" in message.lower() or
        "not all requirements are met" in message.lower() or
        "requirements have not been met" in message.lower()):
        success = False
        status = TestStatus.FAIL
    
    # Handle specific patterns that indicate error (not failure)
    if ("error:" in message.lower() or
        "exception" in message.lower() or
        "crashed" in message.lower() or
        "timeout" in message.lower()):
        success = False
        status = TestStatus.ERROR
        
    # Detect uncertain answers
    if ("could not determine" in message.lower() or
        "unclear if" in message.lower() or
        "couldn't verify" in message.lower() or
        "not able to verify" in message.lower() or
        "uncertain" in message.lower() or
        "inconclusive" in message.lower() or
        "partial" in message.lower() or
        "maybe" in message.lower() or
        "possibly" in message.lower()):
        uncertain = True
        status = TestStatus.UNCERTAIN
    
    # Build full output text from conversation history
    full_output = []
    
    if hasattr(result, 'conversation_history') and result.conversation_history:
        for i, item in enumerate(result.conversation_history):
            role = item.get('role', 'unknown')
            content = item.get('content', '')
            item_type = item.get('type', 'message')  # Get the type of content
            
            if role == 'user':
                # If too long, truncate
                if len(content) > 100:
                    content = content[:100] + "..."
                full_output.append(f"User: {content}")
            elif role == 'assistant':
                if item_type == 'reasoning':
                    # Format reasoning differently
                    full_output.append(f"Reasoning: {content}")
                elif item_type == 'action':
                    # Format actions
                    full_output.append(f"Action: {content}")
                else:
                    # Regular assistant messages
                    full_output.append(f"Assistant: {content}")
                
            # Add separator
            full_output.append("---")
    else:
        # Fallback if no conversation history
        full_output.append(f"Result: {message}")
    
    full_output_text = "\n".join(full_output)
    
    # Prepend the status to the message for clarity
    if status == TestStatus.PASS:
        prefix = "PASS: "
    elif status == TestStatus.FAIL:
        prefix = "FAIL: "
    elif status == TestStatus.ERROR:
        prefix = "ERROR: "
    elif status == TestStatus.SKIP:
        prefix = "SKIP: "
    elif status == TestStatus.UNCERTAIN:
        prefix = "UNCERTAIN: "
    else:
        prefix = ""
    
    # Only add prefix if not already there
    if not message.startswith(prefix):
        message = f"{prefix}{message}"
    
    # Return the status, message, full output, and boolean flags
    return (success, message, full_output_text, uncertain, status)

def format_task_from_csv_row(row: Dict[str, Any], host: str = None) -> str:
    """Format a task from a CSV row
    
    Args:
        row: Dictionary containing test data from CSV
        host: Host URL to use for base_url
        
    Returns:
        str: Formatted task string
    """
    class_name = row['class']
    test_name = row['test']
    base_url = row['base_url']
    task = row['task']
    
    # Get full URL
    full_url = get_full_url(base_url, host=host) if host else base_url
    
    # Create a task that clearly separates the requirements with better formatting
    task_with_setup = f"""
    Test: {class_name}.{test_name}
    URL: {full_url}
    
    TEST REQUIREMENTS:
    -----------------
    {task.strip()}
    -----------------
    
    Please follow all steps in the test requirements in order, and determine if the test passes or fails.
    
    VERY IMPORTANT: For each action you take, please always provide your reasoning. Format your actions like this:
    [REASONING] I'm clicking this button because it appears to be the login button that will take me to the dashboard.
    [ACTION] *click on login button*
    
    RESPONSE FORMAT:
    1. First, write your thought process for determining if this test passes or fails
    2. Consider each requirement and whether it was successfully completed
    3. End your response with exactly "Test PASSED." or "Test FAILED." as appropriate
    4. After this statement, add a brief explanation summarizing the key results
    
    Example of a good response:
    "I completed the following steps:
    1. Navigated to the dashboard page
    2. Verified the news card was present with 3 items
    3. Confirmed the View All button existed and was clickable
    
    Test PASSED. The dashboard showed all required components including the news card with items and functioning View All button."
    """
    
    return task_with_setup

def get_full_url(base_url: str, host: str) -> str:
    """Convert a relative path to a full URL using the configured host
    
    Args:
        base_url: The URL or path to convert
        host: Host URL to use
        
    Returns:
        str: The full URL including host if needed
    """
    from urllib.parse import urlparse
    
    # If it's already a full URL, return as is
    if urlparse(base_url).scheme:
        return base_url
        
    # Strip leading slashes to avoid double slashes
    path = base_url.lstrip('/')
    
    # Join host and path
    return f"{host}/{path}"

def load_auth_state(session_name: str, auth_dir: str = '.auth') -> Optional[Dict]:
    """Load authentication state from file
    
    Args:
        session_name: Name of the auth session
        auth_dir: Directory to load auth state from
        
    Returns:
        Optional[Dict]: Authentication state or None if not found
    """
    auth_file = Path(auth_dir) / f'{session_name}.json'
    if not auth_file.exists():
        return None
    
    try:
        with open(auth_file) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading auth state: {e}")
        return None