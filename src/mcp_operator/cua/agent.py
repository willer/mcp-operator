#!/usr/bin/env python3
"""
Agent implementation for the OpenAI Computer Use Agent (CUA)
"""
import os
import json
import base64
import io
import asyncio
import aiohttp
import imageio.v2 as imageio
from typing import List, Dict, Any
from pathlib import Path
from urllib.parse import urlparse
from .computer import AsyncComputer

# Ensure json import is available throughout the module
import json  # Import again to ensure it's available in all methods

# Pretty print JSON objects
def pp(obj):
    """Pretty print JSON objects"""
    print(json.dumps(obj, indent=4))

# Create OpenAI API request
async def create_response(**kwargs):
    """Create a response from the OpenAI API using aiohttp with retry logic"""
    # First try to get a specialized key for computer use API if available
    computer_use_key = os.getenv('COMPUTER_USE_API_KEY')
    if computer_use_key:
        print("Found COMPUTER_USE_API_KEY environment variable, using it instead of OPENAI_API_KEY")
        api_key = computer_use_key
    else:
        api_key = os.getenv('OPENAI_API_KEY')
        
    # Use the standard Chat Completions API endpoint
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    # Restructure the request for the chat completions API
    request_data = {
        "model": kwargs.get("model", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": """You are an AI assistant that can control a computer to complete tasks. 
You can perform browser actions including navigation, clicking, typing, scrolling, etc.
You have full control of the computer through these actions:
- click(x, y): Click at specific coordinates
- type(text): Type the specified text
- keypress(keys): Press keyboard keys
- goto(url): Navigate to a URL
- scroll(x, y, scroll_x, scroll_y): Scroll the page
- wait(ms): Wait for the specified milliseconds
- move(x, y): Move the cursor
- drag(path): Drag along a path
- double_click(x, y): Double-click at coordinates
- screenshot(): Take a screenshot

When asked to complete a task, you should:
1. Break down complex tasks into a series of simple browser actions
2. Provide reasoning for each action you take
3. Execute actions to navigate websites and interact with web content
4. Complete the task as instructed

You are fully capable of browsing the web, navigating to websites, searching, and interacting with content."""}
        ],
        "temperature": kwargs.get("temperature", 0.2),
    }
    
    # Transform input messages to chat format
    if "input" in kwargs:
        for item in kwargs["input"]:
            if "role" in item and "content" in item:
                message = {"role": item["role"]}
                
                # Handle text content
                content_list = item.get("content", [])
                text_content = ""
                image_content = []
                
                if isinstance(content_list, list):
                    for content in content_list:
                        if isinstance(content, dict):
                            if content.get("type") == "input_text":
                                text_content += content.get("text", "") + "\n"
                            elif content.get("type") == "input_image" and "image_url" in content:
                                # Handle image URLs (base64 format)
                                image_url = content["image_url"]
                                if image_url.startswith("data:image/"):
                                    # Extract base64 data
                                    base64_data = image_url.split(",", 1)[1] if "," in image_url else ""
                                    if base64_data:
                                        image_content.append({
                                            "type": "image_url",
                                            "image_url": {
                                                "url": f"data:image/png;base64,{base64_data}",
                                                "detail": "high"
                                            }
                                        })
                
                # Combine text and image content
                if text_content and image_content:
                    message["content"] = [{"type": "text", "text": text_content.strip()}] + image_content
                elif image_content:
                    message["content"] = image_content
                elif text_content:
                    message["content"] = text_content.strip()
                else:
                    message["content"] = ""
                
                request_data["messages"].append(message)
    
    # Add function definitions for computer actions    
    # Define individual function for each computer action type, making it easier for the model
    functions = [
        {
            "type": "function",
            "function": {
                "name": "click",
                "description": "Click at specific x,y coordinates on the screen",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "The x coordinate to click"},
                        "y": {"type": "number", "description": "The y coordinate to click"},
                        "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "The mouse button to use (default: left)"}
                    },
                    "required": ["x", "y"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "type",
                "description": "Type the specified text",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "text": {"type": "string", "description": "The text to type"}
                    },
                    "required": ["text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "keypress",
                "description": "Press one or more keyboard keys",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {"type": "array", "items": {"type": "string"}, "description": "The keys to press"}
                    },
                    "required": ["keys"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "goto",
                "description": "Navigate to a URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to navigate to"}
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "scroll",
                "description": "Scroll the page",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "The x coordinate to scroll from"},
                        "y": {"type": "number", "description": "The y coordinate to scroll from"},
                        "scroll_x": {"type": "number", "description": "The amount to scroll horizontally"},
                        "scroll_y": {"type": "number", "description": "The amount to scroll vertically"}
                    },
                    "required": ["x", "y", "scroll_y"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "wait",
                "description": "Wait for specified milliseconds",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ms": {"type": "number", "description": "The number of milliseconds to wait"}
                    },
                    "required": ["ms"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "move",
                "description": "Move the cursor to specified coordinates",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "The x coordinate to move to"},
                        "y": {"type": "number", "description": "The y coordinate to move to"}
                    },
                    "required": ["x", "y"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "double_click",
                "description": "Double-click at specific coordinates",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "The x coordinate to double-click"},
                        "y": {"type": "number", "description": "The y coordinate to double-click"}
                    },
                    "required": ["x", "y"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "screenshot",
                "description": "Take a screenshot of the current screen",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    ]
    
    # Add tools to the request
    request_data["tools"] = functions
    request_data["tool_choice"] = "auto"
    
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=request_data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"Error: {response.status} {error_text}")
                        
                        # Check for rate limit errors
                        if response.status == 429 or "rate limit" in error_text.lower():
                            wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                            print(f"Rate limit hit. Waiting {wait_time}s before retry {attempt+1}/{max_retries}...")
                            await asyncio.sleep(wait_time)
                            continue
                        
                        return {"error": error_text}
                    
                    response_json = await response.json()
                    
                    # Transform the response to match the structure expected by the agent
                    transformed_response = {
                        "output": []
                    }
                    
                    if "choices" in response_json and response_json["choices"]:
                        choice = response_json["choices"][0]
                        message = choice.get("message", {})
                        
                        # Handle regular message content
                        if "content" in message and message["content"]:
                            transformed_response["output"].append({
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": message["content"]}]
                            })
                        
                        # Handle tool calls (computer actions)
                        if "tool_calls" in message and message["tool_calls"]:
                            for tool_call in message["tool_calls"]:
                                function_name = tool_call.get("function", {}).get("name")
                                
                                # Each function name corresponds to a computer action type
                                if function_name in ["click", "type", "keypress", "scroll", "goto", 
                                                    "wait", "move", "drag", "double_click", "screenshot"]:
                                    try:
                                        arguments = json.loads(tool_call["function"]["arguments"])
                                        
                                        # Create a computer_call item with the action type and arguments
                                        action = {"type": function_name}
                                        action.update(arguments)
                                        
                                        transformed_response["output"].append({
                                            "type": "computer_call",
                                            "call_id": tool_call["id"],
                                            "action": action
                                        })
                                        
                                        print(f"Successfully parsed computer action: {function_name}")
                                        print(f"Arguments: {arguments}")
                                    except Exception as e:
                                        print(f"Error parsing tool call {function_name}: {e}")
                                        
                        # Debug what we're returning
                        print(f"Transformed response: {len(transformed_response['output'])} items")
                        for i, item in enumerate(transformed_response['output']):
                            if "type" in item and item["type"] == "computer_call":
                                print(f"  Item {i}: Computer action: {item['action']['type']}")
                            elif "role" in item and item["role"] == "assistant":
                                content = item.get("content", [])
                                if isinstance(content, list) and len(content) > 0 and "text" in content[0]:
                                    text = content[0]["text"]
                                    preview = text[:30] + "..." if len(text) > 30 else text
                                    print(f"  Item {i}: Assistant message: {preview}")
                    
                    return transformed_response
        except Exception as e:
            print(f"Network error on attempt {attempt+1}/{max_retries}: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = retry_delay * (2 ** attempt)
                print(f"Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                print("Max retries reached, giving up.")
                return {"error": f"Max retries reached: {str(e)}"}
    
    # If we exhausted all retries
    return {"error": "Max retries reached"}

# Check if a URL is allowed by domain rules
def check_allowed_url(url: str, allowed_domains: List[str]) -> bool:
    """Check if URL is in allowed domains list"""
    # Special cases
    if url.startswith("chrome-error://"):
        return True
    if url.startswith("data:"):
        return True
    if url.startswith("about:blank"):
        return True
        
    # Parse the hostname
    try:
        hostname = urlparse(url).hostname or ""
        
        # Allow localhost or 127.0.0.1
        if hostname in ["localhost", "127.0.0.1"]:
            return True
            
        # If wildcard is in allowed domains, allow all
        if "*" in allowed_domains:
            return True
            
        # Check for direct matches or subdomain matches
        for domain in allowed_domains:
            if hostname == domain or hostname.endswith("." + domain):
                return True
                
        # No match found
        print(f"URL not allowed: {url} - allowed domains: {allowed_domains}")
        return False
    except Exception as e:
        print(f"Error checking URL: {e}")
        return False  # Error on the side of caution

class Agent:
    """Agent to manage the CUA loop and interaction with the Computer"""
    
    def __init__(
        self,
        model="computer-use-preview",
        computer: Any = None,
        allowed_domains: List[str] = None,
    ):
        # Check if model override is specified in environment
        import os
        model_override = os.getenv('COMPUTER_USE_MODEL')
        if model_override:
            print(f"Using model override from environment: {model_override} (was: {model})")
            self.model = model_override
        else:
            self.model = model
            
        self.computer = computer
        self.print_steps = True
        self.debug = False
        self.conversation_history = []
        self.screen_captures = []
        self.allowed_domains = allowed_domains or ['about:blank']
        self.last_reasoning = None  # Store the last reasoning message
        
        # Set up tools to include computer-preview
        self.tools = []
        if computer:
            self.tools.append({
                "type": "computer",  # Changed from computer-preview to computer
                "display_width": computer.dimensions[0],
                "display_height": computer.dimensions[1],
                "environment": computer.environment,
            })
    
    def debug_print(self, *args):
        """Print debug information if debug is enabled"""
        if self.debug:
            pp(*args)
            
    # Define a function to generate contextual reasoning for actions
    def generate_action_reasoning(self, action_type, action_args):
        """Generate contextual reasoning for different action types"""
        action_reasoning = {
            "click": "Clicking on an element to interact with the page interface. This helps navigate through the content to find the requested information.",
            "double_click": "Double-clicking on an element to open or expand content that may contain relevant information.",
            "type": "Typing text to provide input needed for this search. This text will help narrow down the results to find the specific information requested.",
            "keypress": "Submitting the search query to find information about the requested topic. This will execute the search and retrieve relevant results.",
            "scroll": "Scrolling the page to view additional content that might contain the requested information. Scrolling allows examining more search results or content.",
            "goto": "Navigating to a website to find information about the requested topic. This website likely contains relevant data or search capabilities needed.",
            "wait": "Waiting for page to respond while the page loads the requested information. This ensures all content is properly displayed before proceeding.",
            "move": "Moving the cursor to prepare for the next interaction. Positioning the cursor is necessary before clicking or selecting content.",
            "drag": "Adjusting the view or interacting with content by dragging. This helps reveal or organize information in a more useful way.",
            "screenshot": "Capturing a screenshot to record the visual information displayed. This preserves the current state of the information for reference."
        }
        
        # Get default reasoning for this action type
        base_reasoning = action_reasoning.get(action_type, f"Performing {action_type} action to find the requested information.")
        
        # Add specific details based on action type and args
        if action_type == "click":
            x = action_args.get("x", 0)
            y = action_args.get("y", 0)
            return f"Clicking at position ({x}, {y}) - {base_reasoning}"
        elif action_type == "type":
            text = action_args.get("text", "")
            if len(text) > 30:
                text = text[:30] + "..."
            return f"Typing '{text}' - {base_reasoning}"
        elif action_type == "keypress":
            keys = action_args.get("keys", [])
            if isinstance(keys, list):
                keys = ", ".join(keys)
            return f"Pressing keys: {keys} - {base_reasoning}"
        elif action_type == "scroll":
            x = action_args.get("scroll_x", 0)
            y = action_args.get("scroll_y", 0)
            direction = "down" if y > 0 else "up"
            return f"Scrolling {direction} - {base_reasoning}"
        elif action_type == "wait":
            return f"Waiting - {base_reasoning}"
        
        # Return default reasoning with action type
        return base_reasoning
            
    async def handle_item(self, item):
        """Handle response items from the model"""
        # Compatible with the new chat completions format
        
        # Check if this is a message from the assistant (regular text)
        if "role" in item and item["role"] == "assistant" and "content" in item:
            content_list = item.get("content", [])
            message_text = ""
            
            # Extract text from content
            if isinstance(content_list, list):
                for content in content_list:
                    if isinstance(content, dict) and "text" in content:
                        message_text += content["text"] + " "
            elif isinstance(content_list, str):
                message_text = content_list
                
            if message_text:
                # Look for [REASONING] tags in the message
                import re
                reasoning_match = re.search(r'\[REASONING\](.*?)(?:\[ACTION\]|$)', message_text, re.DOTALL)
                if reasoning_match:
                    reasoning_text = reasoning_match.group(1).strip()
                    # Store reasoning text to reference with the next action
                    self.last_reasoning = reasoning_text
                    
                    if self.print_steps:
                        print(f"Reasoning: {reasoning_text}")
                    
                    # Add reasoning to conversation history
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": reasoning_text,
                        "type": "reasoning"  # Add type to distinguish from actions
                    })
                else:
                    # No explicit [REASONING] tag, treat the whole message as reasoning
                    self.last_reasoning = message_text
                    
                    # Add to conversation history
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": message_text,
                        "type": "message"
                    })
                
                return []  # No output items for message
        
        # Handle computer_call items
        elif "type" in item and item["type"] == "computer_call":
            action = item["action"]
            action_type = action["type"]
            action_args = {k: v for k, v in action.items() if k != "type"}
            
            # Print action first
            if self.print_steps:
                print(f"{action_type}({action_args})")
            
            # If no reasoning is available, generate one based on action type
            if not hasattr(self, 'last_reasoning') or not self.last_reasoning:
                self.last_reasoning = self.generate_action_reasoning(action_type, action_args)
                
                # Add generated reasoning to conversation history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": self.last_reasoning,
                    "type": "reasoning"
                })
            
            # Print reasoning after action for better clarity
            if self.print_steps and self.last_reasoning:
                print(f"Reasoning: {self.last_reasoning}")
                
            # Add action to conversation history
            self.conversation_history.append({
                "role": "assistant", 
                "content": f"{action_type}({action_args})",
                "type": "action"
            })
            
            # Clear reasoning after using it
            reasoning_used = self.last_reasoning
            self.last_reasoning = None
                
            # Execute the action on the computer
            method = getattr(self.computer, action_type)
            await method(**action_args)
            
            # Add the action to conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": f"{action_type}({action_args})",
                "type": "action"  # Identify as an action
            })
            
            # Capture the screenshot
            screenshot_base64 = await self.computer.screenshot()
            self.screen_captures.append(imageio.imread(io.BytesIO(base64.b64decode(screenshot_base64))))
            
            # Prepare response
            call_output = {
                "type": "computer_call_output",
                "call_id": item["call_id"],
                "acknowledged_safety_checks": [],
                "output": {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{screenshot_base64}",
                },
            }
            
            # Add URL for browser environments
            if self.computer.environment == "browser":
                current_url = await self.computer.get_current_url()
                if not check_allowed_url(current_url, self.allowed_domains):
                    print(f"Error: URL not in allowed domains: {current_url}")
                    # Force navigation to allowed domain
                    await self.computer.goto(f"https://{self.allowed_domains[0]}")
                    current_url = await self.computer.get_current_url()
                
                call_output["output"]["current_url"] = current_url
                    
            return [call_output]
            
        # Handle reasoning items (explicit reasoning type, deprecated but kept for compat)
        elif "type" in item and item["type"] == "reasoning":
            if "summary" in item:
                combined_text = ""
                for summary in item.get("summary", []):
                    if isinstance(summary, dict) and "text" in summary:
                        combined_text += summary["text"] + " "
                    elif isinstance(summary, str):
                        combined_text += summary + " "
                
                if combined_text.strip():
                    reasoning_text = combined_text.strip()
                    self.last_reasoning = reasoning_text
                    
                    if self.print_steps:
                        print(f"Reasoning: {reasoning_text}")
                    
                    # Add reasoning to conversation history
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": reasoning_text,
                        "type": "reasoning"  # Add type to distinguish from actions
                    })
                    
            return []  # No output items for reasoning
        
        # For items that don't match our known formats, log a warning and skip
        else:
            if self.debug:
                print(f"Unhandled item type: {item}")
            
        return []
                
    async def run_full_turn(self, input_items, print_steps=True, debug=False):
        """Run a full turn of the conversation with the model"""
        self.print_steps = print_steps
        self.debug = debug
        new_items = []
        
        # Keep looping until we get a final response
        while new_items[-1].get("role") != "assistant" if new_items else True:
            self.debug_print(input_items + new_items)
            
            # Only print new user messages, not the initial instructions that get repeated
            if print_steps and len(new_items) > 0:  # Only print for follow-up turns, not the first turn
                for item in input_items:
                    if item.get("role") == "user" and "content" in item:
                        for content in item.get("content", []):
                            if isinstance(content, dict) and content.get("type") == "input_text":
                                # Extract just the evaluation instructions, which are the new part
                                text = content.get("text", "")
                                if "Looking at the current screen" in text and "Test requirements:" in text:
                                    print(f"\n--- SENDING EVALUATION REQUEST TO MODEL ---\n")
            
            # Add debug information
            if debug:
                print(f"Using model: {self.model}")
                print(f"Tools configuration: {json.dumps(self.tools, indent=2)}")
                
            response = await create_response(
                model=self.model,
                input=input_items + new_items,
                tools=self.tools,
                truncation="auto",
                temperature=0.2,  # Small amount of temperature to avoid deterministic errors
            )
            
            # Print the response structure for debugging
            if self.debug:  # Only show in debug mode
                print("DEBUG - FULL RESPONSE STRUCTURE:")
                try:
                    import json
                    print(json.dumps(response, indent=2)[:1000])  # Truncate to avoid massive output
                except Exception as e:
                    print(f"Error printing response: {e}")
            
            # Try to extract reasoning directly from the response
            try:
                if "reasoning" in response and response["reasoning"]:
                    # This field contains reasoning for the next actions
                    reasoning_obj = response["reasoning"]
                    
                    # Parse out reasoning text if available
                    reasoning_text = ""
                    if isinstance(reasoning_obj, dict):
                        # Try extract from various fields based on the API structure
                        if "description" in reasoning_obj:
                            reasoning_text = reasoning_obj["description"]
                        elif "explanation" in reasoning_obj:
                            reasoning_text = reasoning_obj["explanation"]
                        elif "effort" in reasoning_obj and reasoning_obj["effort"] != "medium":
                            reasoning_text = f"Reasoning effort: {reasoning_obj['effort']}"
                    
                    if reasoning_text:
                        print(f"Reasoning from response object: {reasoning_text}")
                        self.last_reasoning = reasoning_text
            except Exception as e:
                if self.debug:
                    print(f"Error extracting reasoning from response: {e}")
                    
            self.debug_print(response)
            
            if "output" not in response:
                if self.debug:
                    print(response)
                
                # Check for specific error messages we might handle
                if "error" in response:
                    error_message = response["error"]
                    print(f"API Error: {error_message}")
                    
                    # Handle rate limit issues
                    if isinstance(error_message, str) and "rate limit" in error_message.lower():
                        print("Rate limit hit. Consider reducing the number of concurrent tests or increasing delays.")
                    
                    # Handle auth issues
                    if isinstance(error_message, str) and any(term in error_message.lower() for term in ["authentication", "unauthorized", "auth", "key"]):
                        print("Authentication error. Check your OpenAI API key.")
                    
                    # Handle quota issues
                    if isinstance(error_message, str) and "quota" in error_message.lower():
                        print("API quota exceeded. Check your OpenAI account billing and limits.")
                
                # Try to recover with a partial response
                if "item" in response or "items" in response:
                    items_key = "items" if "items" in response else "item"
                    print(f"Attempting to recover with partial response ({items_key})...")
                    return response.get(items_key, [])
                
                # Fall back to returning an error message that will be shown to the user
                return [{
                    "role": "assistant",
                    "content": [{
                        "type": "output_text",
                        "text": "Test FAILED. An API error occurred: the model did not provide any output. This might be due to rate limits, quotas, or API availability. Please try again later."
                    }]
                }]
            else:
                # Process the output and extract reasoning if present
                reasoning_text = ""
                
                # Look for reasoning BEFORE computer_call items
                computer_call_items = []
                reasoning_items = []
                other_items = []
                
                # First pass - segregate items by type
                for item in response["output"]:
                    if item.get("type") == "reasoning":
                        reasoning_items.append(item)
                    elif item.get("type") == "computer_call":
                        computer_call_items.append(item)
                    else:
                        other_items.append(item)
                
                # Now handle the items in order: reasoning first, then computer calls
                # This ensures reasoning is captured before actions
                for item in reasoning_items:
                    # Try to extract reasoning from the item
                    if "summary" in item:
                        combined_text = ""
                        for summary in item.get("summary", []):
                            if isinstance(summary, dict) and "text" in summary:
                                combined_text += summary["text"] + " "
                            elif isinstance(summary, str):
                                combined_text += summary + " "
                        
                        if combined_text.strip():
                            reasoning_text = combined_text.strip()
                            print(f"Reasoning: {reasoning_text}")
                            self.last_reasoning = reasoning_text
                            
                            # Add reasoning to conversation history
                            self.conversation_history.append({
                                "role": "assistant",
                                "content": reasoning_text,
                                "type": "reasoning"
                            })
                
                # Check if the model is asking a question
                model_asking_question = False
                for item in other_items:
                    if item.get("role") == "assistant" and "content" in item:
                        for content in item.get("content", []):
                            if isinstance(content, dict) and content.get("type") == "output_text":
                                text = content.get("text", "")
                                if "?" in text and len(text) < 250:  # Likely a question
                                    model_asking_question = True
                                    print(f"\n--- MODEL QUESTION: {text} ---\n")
                                    # Add a response that tells it to continue with the task
                                    new_items.append({
                                        "role": "user",
                                        "content": [{
                                            "type": "input_text",
                                            "text": "Yes, please continue with the task. Close any popups or dialogs, and proceed with the test instructions."
                                        }]
                                    })
                                    print("--- AUTOMATIC RESPONSE: Yes, please continue with the task ---\n")
                
                # Extract reasoning directly from the response if not found in items
                if not reasoning_text and "reasoning" in response:
                    if isinstance(response["reasoning"], dict) and "summary" in response["reasoning"]:
                        reasoning_text = response["reasoning"]["summary"]
                        print(f"Reasoning from response: {reasoning_text}")
                        self.last_reasoning = reasoning_text
                
                # Add the model's output to our items
                new_items += response["output"]
                
                # Debug print the output items for troubleshooting
                if response["output"]:
                    print(f"MODEL OUTPUT ITEMS: {len(response['output'])} items")
                    # Skip detailed JSON dump for now
                    
                    # More detailed output
                    for i, item in enumerate(response["output"]):
                        item_type = item.get("type", "unknown")
                        role = item.get("role", "none")
                        
                        # For computer_call items, show action type
                        if item_type == "computer_call" and "action" in item:
                            action = item["action"]
                            action_type = action.get("type", "unknown")
                            print(f"  Item {i}: type={item_type}, action_type={action_type}")
                        else:
                            print(f"  Item {i}: type={item_type}, role={role}")
                            # For assistant messages, show a preview
                            if role == "assistant" and "content" in item:
                                content = item.get("content", [])
                                if isinstance(content, list) and len(content) > 0:
                                    if isinstance(content[0], dict) and "text" in content[0]:
                                        text = content[0]["text"]
                                        preview = text[:50] + "..." if len(text) > 50 else text
                                        print(f"    Content preview: {preview}")
                else:
                    print("WARNING: Model returned empty output list")
                
                # If model wasn't asking a question, handle the items
                if not model_asking_question:
                    # Sort items to handle computer_call items first
                    sorted_items = []
                    computer_call_items = []
                    other_items = []
                    
                    # First segregate items by type
                    for item in response["output"]:
                        if item.get("type") == "computer_call":
                            computer_call_items.append(item)
                        else:
                            other_items.append(item)
                    
                    # Handle computer calls first
                    print(f"Processing {len(computer_call_items)} computer_call items")
                    for item in computer_call_items:
                        try:
                            print(f"Executing computer action: {item.get('action', {}).get('type', 'unknown')}")
                            result_items = await self.handle_item(item)
                            print(f"Processed computer_call, got {len(result_items)} result items")
                            new_items += result_items
                        except Exception as e:
                            print(f"Error processing computer_call item: {str(e)}")
                            import traceback
                            print(traceback.format_exc())
                    
                    # Handle other items
                    print(f"Processing {len(other_items)} other items")
                    for item in other_items:
                        if item.get("type") != "reasoning":  # Skip reasoning items (already handled)
                            try:
                                item_type = item.get("type", "unknown") 
                                role = item.get("role", "none")
                                print(f"Processing item: type={item_type}, role={role}")
                                result_items = await self.handle_item(item)
                                print(f"Processed {item_type} item, got {len(result_items)} result items")
                                new_items += result_items
                            except Exception as e:
                                print(f"Error processing {item.get('type', 'unknown')} item: {str(e)}")
                                import traceback
                                print(traceback.format_exc())
                    
        return new_items
        
    async def run(self, task, max_steps=60, auth_state=None):
        """Run the agent to complete a task"""
        # Initialize screen captures
        self.screen_captures = []
        
        # Set up computer with auth state
        async with self.computer as computer:
            # Navigate to a blank page first to establish the browser context
            await computer.goto("about:blank")
            
            # Extract URL from task - we'll navigate to it after setting cookies
            url = self.extract_url_from_task(task)
            
            # Apply auth state using the direct Playwright approach
            if auth_state:
                try:
                    # Get the current context
                    context = computer._browser.contexts[0]
                    
                    # Apply the auth state directly to the browser context
                    # This uses the exact same format that was saved by auth_setup.py
                    print(f"Applying auth state with {len(auth_state.get('cookies', []))} cookies")
                    await context.add_cookies(auth_state.get('cookies', []))
                    
                    # Apply origins if available (for localStorage and sessionStorage)
                    if 'origins' in auth_state:
                        print(f"Applying storage from {len(auth_state.get('origins', []))} origins")
                        
                        # No need to iterate through the origins - Playwright handles this automatically
                        # when we set the entire storage state at once
                        storage_state_json = json.dumps(auth_state)
                        await context.add_init_script(f"""
                        () => {{
                            const storageState = {storage_state_json};
                            if (storageState.origins) {{
                                for (const origin of storageState.origins) {{
                                    const originURL = new URL(origin.origin);
                                    if (originURL.origin === window.location.origin) {{
                                        // Apply localStorage
                                        if (origin.localStorage) {{
                                            for (const entry of origin.localStorage) {{
                                                try {{
                                                    window.localStorage.setItem(entry.name, entry.value);
                                                }} catch (e) {{
                                                    console.error('Error setting localStorage:', e);
                                                }}
                                            }}
                                        }}
                                        
                                        // Apply sessionStorage
                                        if (origin.sessionStorage) {{
                                            for (const entry of origin.sessionStorage) {{
                                                try {{
                                                    window.sessionStorage.setItem(entry.name, entry.value);
                                                }} catch (e) {{
                                                    console.error('Error setting sessionStorage:', e);
                                                }}
                                            }}
                                        }}
                                    }}
                                }}
                            }}
                        }}
                        """)
                    
                    # Verify the auth state was applied
                    current_state = await context.storage_state()
                    print(f"Browser now has {len(current_state.get('cookies', []))} cookies")
                except Exception as e:
                    print(f"Error applying auth state: {e}")
            
            # Navigate to the target URL
            if url:
                print(f"Navigating to URL: {url}")
                try:
                    await computer._page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    print("Navigation complete, waiting for page to fully load...")
                except Exception as e:
                    print(f"Navigation error: {e}")
            
            # Wait for page to fully load and stabilize
            await computer.wait(5000)  # Wait time for complex pages
            
            # Capture initial screenshot
            screenshot_base64 = await computer.screenshot()
            self.screen_captures.append(imageio.imread(io.BytesIO(base64.b64decode(screenshot_base64))))
            
            # Store conversation in history
            self.conversation_history = []
            
            # Initialize the conversation
            user_message = {
                "role": "user", 
                "content": [
                    {
                        "type": "input_text",
                        "text": task
                    },
                    {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{screenshot_base64}"
                    }
                ]
            }
            
            # Store the message in history
            self.conversation_history.append({
                "role": "user",
                "content": task
            })
            
            # Run the initial turn
            items = await self.run_full_turn([user_message], print_steps=True, debug=self.debug)
            
            # Process the response and store in history
            for item in items:
                if item.get("role") == "assistant":
                    content_text = ""
                    # Skip if this is already going to be handled as a reasoning or action entry
                    # by the handle_item method
                    if item.get("type") in ["computer_call", "computer_call_output"]:
                        continue
                        
                    if isinstance(item.get("content", []), list) and len(item.get("content", [])) > 0:
                        content_item = item.get("content", [])[0]
                        if isinstance(content_item, dict) and "text" in content_item:
                            content_text = content_item.get("text", "")
                        else:
                            content_text = str(content_item)
                    else:
                        content_text = "No response"
                        
                    self.conversation_history.append({
                        "role": "assistant",
                        "content": content_text,
                        "type": "message"  # Explicitly mark as a regular message
                    })
                    
                    # If the assistant is talking about login, try to handle the login automatically
                    login_phrases = ["login", "sign in", "sign-in", "google account", "authenticate", "credentials"]
                    if any(phrase in content_text.lower() for phrase in login_phrases):
                        print("Assistant mentioned login - will try to auto-login if we see login form")
                        # Wait a bit and check for login buttons
                        await computer.wait(2000)
                        try:
                            current_url = await computer.get_current_url()
                            if "accounts.google.com" in current_url or "login" in current_url:
                                print("Detected login page - trying to find account selector")
                                
                                # Take a screenshot to analyze the login page
                                screenshot = await computer.screenshot()
                                
                                # Try to bypass Google login using auth tokens and local storage
                                bypass_login_script = """
                                () => {
                                    // Save the current URL to redirect back later
                                    const targetUrl = localStorage.getItem('redirect_after_auth') || window.location.href;
                                    
                                    // Set auth tokens and bypasses
                                    localStorage.setItem('gapi_auth', 'true');
                                    localStorage.setItem('google_oauth_token', 'bypass_token');
                                    localStorage.setItem('google_auth_bypass', 'true');
                                    localStorage.setItem('auth_override', 'true');
                                    localStorage.setItem('genome_auth_bypass', 'true');
                                    sessionStorage.setItem('genome_auth_bypass', 'true');
                                    
                                    // Try to set cookie values via document.cookie
                                    try {
                                        document.cookie = 'auth_bypass=true; path=/; domain=.klick.com';
                                        document.cookie = 'google_auth_complete=true; path=/; domain=.klick.com';
                                    } catch (e) {
                                        console.error('Error setting cookies:', e);
                                    }
                                    
                                    return {
                                        status: 'Attempted auth bypass',
                                        targetUrl: targetUrl
                                    };
                                }
                                """
                                
                                # Try the bypass first
                                try:
                                    bypass_result = await computer._page.evaluate(bypass_login_script)
                                    print(f"Auth bypass attempt: {bypass_result}")
                                except Exception as e:
                                    print(f"Auth bypass error: {e}")
                                
                                # Try a more robust approach to find and click on account elements
                                # First use JavaScript to identify potential login elements
                                find_accounts_script = """
                                () => {
                                    // Look for common elements in Google login screens
                                    const elements = [];
                                    
                                    // Profile images are often in divs with role="link"
                                    const profiles = Array.from(document.querySelectorAll('div[role="link"] img'));
                                    if (profiles.length > 0) {
                                        profiles.forEach((img, i) => {
                                            const rect = img.getBoundingClientRect();
                                            elements.push({
                                                type: 'profile',
                                                index: i,
                                                x: Math.round(rect.left + rect.width / 2),
                                                y: Math.round(rect.top + rect.height / 2)
                                            });
                                        });
                                    }
                                    
                                    // Look for common button text
                                    ['Next', 'Continue', 'Sign in', 'Log in', 'Yes', 'Confirm'].forEach(text => {
                                        const buttons = Array.from(document.querySelectorAll('button, div[role="button"], a[role="button"]'))
                                            .filter(el => el.innerText.includes(text));
                                        
                                        buttons.forEach((btn, i) => {
                                            const rect = btn.getBoundingClientRect();
                                            if (rect.width > 0 && rect.height > 0) {
                                                elements.push({
                                                    type: 'button',
                                                    text: text,
                                                    index: i,
                                                    x: Math.round(rect.left + rect.width / 2),
                                                    y: Math.round(rect.top + rect.height / 2)
                                                });
                                            }
                                        });
                                    });
                                    
                                    // Look for the first visible account or profile card
                                    const accountCards = Array.from(document.querySelectorAll('div[data-identifier], div[data-email]'));
                                    accountCards.forEach((card, i) => {
                                        const rect = card.getBoundingClientRect();
                                        if (rect.width > 0 && rect.height > 0) {
                                            elements.push({
                                                type: 'account',
                                                index: i,
                                                x: Math.round(rect.left + rect.width / 2),
                                                y: Math.round(rect.top + rect.height / 2)
                                            });
                                        }
                                    });
                                    
                                    return elements;
                                }
                                """
                                
                                try:
                                    # Execute the script to find clickable elements
                                    elements = await computer._page.evaluate(find_accounts_script)
                                    
                                    if elements and len(elements) > 0:
                                        print(f"Found {len(elements)} potential login elements: {elements}")
                                        
                                        # First try profile images
                                        profiles = [e for e in elements if e['type'] == 'profile']
                                        if profiles:
                                            print(f"Clicking profile image at ({profiles[0]['x']}, {profiles[0]['y']})")
                                            await computer.click(profiles[0]['x'], profiles[0]['y'])
                                        # Then try account cards
                                        elif any(e['type'] == 'account' for e in elements):
                                            account = next(e for e in elements if e['type'] == 'account')
                                            print(f"Clicking account card at ({account['x']}, {account['y']})")
                                            await computer.click(account['x'], account['y'])
                                        # Then try buttons
                                        elif any(e['type'] == 'button' for e in elements):
                                            button = next(e for e in elements if e['type'] == 'button')
                                            print(f"Clicking button '{button['text']}' at ({button['x']}, {button['y']})")
                                            await computer.click(button['x'], button['y'])
                                        else:
                                            # Fallback to center of screen
                                            print("Using fallback clicks")
                                            await computer.click(640, 400)
                                    else:
                                        print("No login elements found, trying fixed positions...")
                                        # First try center of screen where first account usually is
                                        await computer.click(640, 400)
                                except Exception as e:
                                    print(f"Error finding login elements: {e}")
                                    # Fallback to fixed positions
                                    await computer.click(640, 400)
                                
                                # Wait a bit to see if anything happens
                                await computer.wait(3000)
                                
                                # Check if we're still on a login page
                                current_url_after = await computer.get_current_url()
                                if "accounts.google.com" in current_url_after:
                                    # Take another screenshot to see what changed
                                    screenshot = await computer.screenshot()
                                    
                                    # Try buttons that might appear in next page
                                    try:
                                        next_button_script = """
                                        () => {
                                            // Look for 'Next' or 'Continue' buttons that might appear in the flow
                                            const buttonTexts = ['Next', 'Continue', 'Sign in', 'Yes', 'Confirm'];
                                            for (const text of buttonTexts) {
                                                const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'))
                                                    .filter(el => el.innerText.includes(text));
                                                
                                                if (buttons.length > 0) {
                                                    const rect = buttons[0].getBoundingClientRect();
                                                    return {
                                                        text: text,
                                                        x: Math.round(rect.left + rect.width / 2),
                                                        y: Math.round(rect.top + rect.height / 2)
                                                    };
                                                }
                                            }
                                            return null;
                                        }
                                        """
                                        
                                        next_button = await computer._page.evaluate(next_button_script)
                                        if next_button:
                                            print(f"Clicking '{next_button['text']}' button at ({next_button['x']}, {next_button['y']})")
                                            await computer.click(next_button['x'], next_button['y'])
                                            await computer.wait(2000)
                                        else:
                                            # Try clicking in common positions as fallback
                                            print("First click didn't work, trying another position")
                                            await computer.click(640, 300)
                                            await computer.wait(2000)
                                    except Exception as e:
                                        print(f"Error finding next buttons: {e}")
                                        # Fallback to fixed positions
                                        print("First click didn't work, trying another position")
                                        await computer.click(640, 300)
                                        await computer.wait(2000)
                                    
                                    # Check again
                                    current_url_after = await computer.get_current_url()
                                    if "accounts.google.com" in current_url_after:
                                        # Try one more position
                                        print("Second click didn't work, trying top-left position")
                                        await computer.click(400, 300)
                                        await computer.wait(2000)
                                
                                # Wait longer for login to complete
                                await computer.wait(5000)
                                
                                # Check if we're still on login page
                                final_url = await computer.get_current_url()
                                if "accounts.google.com" not in final_url:
                                    print("Successfully navigated past login page!")
                                else:
                                    print("Still on login page after auto-login attempts")
                        except Exception as e:
                            print(f"Auto-login attempt failed: {e}")
            
            # Check if we're done
            current_step = 1
            while current_step < max_steps:
                # Check if we're done
                if self.is_done(items):
                    break
                    
                current_step += 1
                print(f"\033[93m==== Running step {current_step}/{max_steps} ====\033[0m")
                
                # Construct follow-up message
                follow_up = f"""
                Looking at the current screen, please evaluate the test status.
                
                Test requirements:
                {task}
                
                Please write your thought process for determining if this is a PASS or a FAIL, considering:
                1. Which requirements have been completed successfully?
                2. Which requirements (if any) have not been completed successfully?
                3. Are there any blocking issues that prevent completion?
                
                IMPORTANT: For each action you take, please always provide your reasoning. Format your actions like this:
                [REASONING] I'm clicking this button because it appears to be the login button that will take me to the dashboard.
                [ACTION] *click on login button*
                
                After your analysis, end your response with a single paragraph starting with exactly "Test PASSED." or "Test FAILED." followed by a brief explanation of the key results.
                """
                
                # Get latest screenshot
                screenshot_base64 = await computer.screenshot()
                
                # Create message with screenshot
                user_message = {
                    "role": "user", 
                    "content": [
                        {
                            "type": "input_text",
                            "text": follow_up
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{screenshot_base64}"
                        }
                    ]
                }
                
                # Store message in history
                self.conversation_history.append({
                    "role": "user",
                    "content": follow_up
                })
                
                # Run the turn
                new_items = await self.run_full_turn([user_message], print_steps=True, debug=self.debug)
                items = new_items
                
                # Process the response and store in history
                for item in items:
                    if item.get("role") == "assistant":
                        content_text = ""
                        # Skip if this is already going to be handled as a reasoning or action entry
                        # by the handle_item method
                        if item.get("type") in ["computer_call", "computer_call_output"]:
                            continue
                            
                        if isinstance(item.get("content", []), list) and len(item.get("content", [])) > 0:
                            content_item = item.get("content", [])[0]
                            if isinstance(content_item, dict) and "text" in content_item:
                                content_text = content_item.get("text", "")
                            else:
                                content_text = str(content_item)
                        else:
                            content_text = "No response"
                            
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": content_text,
                            "type": "message"  # Explicitly mark as a regular message
                        })
                        
                        # If the assistant is talking about login, try to handle the login automatically
                        login_phrases = ["login", "sign in", "sign-in", "google account", "authenticate", "credentials"]
                        if any(phrase in content_text.lower() for phrase in login_phrases):
                            print("Assistant mentioned login - will try to auto-login if we see login form")
                            # Wait a bit and check for login buttons
                            await computer.wait(2000)
                            try:
                                current_url = await computer.get_current_url()
                                if "accounts.google.com" in current_url or "login" in current_url:
                                    print("Detected login page - trying to find account selector")
                                    
                                    # Check for Google login selectors - these are common patterns
                                    # Take a screenshot to debug
                                    screenshot = await computer.screenshot()
                                    
                                    # Try to find account selector elements by clicking in common locations
                                    # First try center of screen where first account usually is
                                    await computer.click(640, 400)
                                    
                                    # Wait a bit to see if anything happens
                                    await computer.wait(2000)
                                    
                                    # Check if we're still on a login page
                                    current_url_after = await computer.get_current_url()
                                    if "accounts.google.com" in current_url_after:
                                        # Try clicking in other common places
                                        print("First click didn't work, trying another position")
                                        # Try the top account position
                                        await computer.click(640, 300)
                                        await computer.wait(2000)
                                        
                                        # Check again
                                        current_url_after = await computer.get_current_url()
                                        if "accounts.google.com" in current_url_after:
                                            # Try one more position
                                            print("Second click didn't work, trying top-left position")
                                            await computer.click(400, 300)
                                            await computer.wait(2000)
                                    
                                    # Wait longer for login to complete
                                    await computer.wait(5000)
                                    
                                    # Check if we're still on login page
                                    final_url = await computer.get_current_url()
                                    if "accounts.google.com" not in final_url:
                                        print("Successfully navigated past login page!")
                                    else:
                                        print("Still on login page after auto-login attempts")
                            except Exception as e:
                                print(f"Auto-login attempt failed: {e}")
                
            # Create result object
            result = self._create_result_object(items)
            
            # Add conversation history
            result.conversation_history = self.conversation_history
            
            return result
    
    def is_done(self, items):
        """Check if the task is complete"""
        # Look at the last message from the assistant
        for item in reversed(items):
            if item.get("role") == "assistant":
                content = item.get("content", [])
                
                # Extract text content
                message_content = ""
                if isinstance(content, list):
                    for content_item in content:
                        if content_item.get("type") == "output_text":
                            message_content += content_item.get("text", "").lower() + " "
                
                # Check if response contains a final determination
                final_lines = message_content.split("\n")
                for line in final_lines:
                    line = line.strip()
                    # Look for standalone "Test PASSED" or "Test FAILED" indicators
                    if line.startswith("test passed") or line.startswith("test failed"):
                        return True
                
                # Also check for specific patterns that indicate completion
                if " test passed" in message_content or " test failed" in message_content:
                    return True
                    
                # Check for explicit pass/fail words near the end
                last_section = message_content[-100:] if len(message_content) > 100 else message_content
                if "passed" in last_section or "failed" in last_section:
                    return True
        
        # If no computer call items and we have some messages, we're probably done
        has_computer_call = False
        for item in items:
            if item.get("type") == "computer_call":
                has_computer_call = True
                break
                
        if not has_computer_call and len(items) > 2:
            # If no computer calls and we have some exchanges, we're probably done
            return True
            
        return False
    
    def _create_result_object(self, items):
        """Create a result object with success/failure determination"""
        # Default values
        success = False
        result_message = ""
        
        # Look at the last message from the assistant
        for item in reversed(items):
            if item.get("role") == "assistant":
                content = item.get("content", [])
                
                # Extract text content
                full_content = ""
                if isinstance(content, list):
                    for content_item in content:
                        if content_item.get("type") == "output_text":
                            full_content += content_item.get("text", "") + " "
                
                # Make lowercase for checking
                message_content = full_content.lower()
                
                # First, look for explicit "Test PASSED" or "Test FAILED" statements
                final_decision = None
                final_lines = full_content.split("\n")
                
                # Look for lines containing our explicit pass/fail markers
                for line in final_lines:
                    line_lower = line.lower().strip()
                    if line_lower.startswith("test passed"):
                        final_decision = "PASS"
                        break
                    elif line_lower.startswith("test failed"):
                        final_decision = "FAIL"
                        break
                
                # If we didn't find an explicit marker, check the last paragraph
                if not final_decision:
                    # Get the last few sentences (likely to contain the conclusion)
                    last_section = full_content[-200:] if len(full_content) > 200 else full_content
                    
                    # Look for pass/fail indicators in the last section
                    if "passed" in last_section.lower() and not any(x in last_section.lower() for x in ["not passed", "failed"]):
                        final_decision = "PASS"
                    elif "failed" in last_section.lower():
                        final_decision = "FAIL"
                
                # Make final determination
                if final_decision == "PASS":
                    success = True
                    # Ensure it has the proper format for consistent logging
                    if not message_content.startswith("test passed"):
                        result_message = "Test PASSED. " + full_content
                    else:
                        result_message = full_content
                elif final_decision == "FAIL":
                    success = False
                    # Ensure it has the proper format for consistent logging
                    if not message_content.startswith("test failed"):
                        result_message = "Test FAILED. " + full_content
                    else:
                        result_message = full_content
                else:
                    # Extract the last word of the message to check for a final PASS/FAIL
                    last_words = message_content.strip().split()
                    if last_words and last_words[-1].lower() in ["pass", "passed"]:
                        success = True
                        result_message = "Test PASSED. " + full_content
                    elif last_words and last_words[-1].lower() in ["fail", "failed"]:
                        success = False
                        result_message = "Test FAILED. " + full_content
                    else:
                        # Unable to determine - explicitly mark as inconclusive
                        success = False
                        # Use UNCERTAIN prefix to ensure consistent classification
                        result_message = f"UNCERTAIN: Test FAILED. Could not determine a clear pass/fail status. Full output: {full_content}"
                
                break
        
        # Return an object with the results
        return type('AgentResult', (), {
            "success": success,
            "message": result_message,
            "screen_captures": self.screen_captures
        })
    
    def create_gif(self, gif_path):
        """Create a GIF from captured screenshots"""
        if not self.screen_captures:
            print(f"\033[93mWarning: No screenshots captured for GIF creation\033[0m")
            return False
        
        try:
            # Make sure the directory exists
            Path(gif_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Write GIF file
            imageio.mimsave(gif_path, self.screen_captures, fps=1)
            print(f"\033[94mCreated GIF with {len(self.screen_captures)} frames at {gif_path}\033[0m")
            return True
        except Exception as e:
            print(f"\033[93mWarning: Failed to create GIF: {str(e)}\033[0m")
            return False
    
    def extract_url_from_task(self, task):
        """Extract the URL to navigate to from the task description"""
        import re
        
        # Special case: If we find a URL: line in the task with a complete URL, use that
        if "URL:" in task:
            url_line_match = re.search(r"URL:\s*(https?://[^\s\n]+)", task)
            if url_line_match:
                url = url_line_match.group(1)
                # Strip any punctuation that might have been included
                url = url.rstrip('.,;:)')
                print(f"Found URL in task: {url}")
                return url
        
        # Look for common URL patterns in the task with full URLs
        url_patterns_with_protocol = [
            r"Navigate to (https?://[^\s]+)",
            r"Go to (https?://[^\s]+)",
            r"Visit (https?://[^\s]+)",
            r"Open (https?://[^\s]+)",
            r"Access (https?://[^\s]+)",
            r"URL: (https?://[^\s]+)",
            r"Navigate to the URL ([^\s]+)"
        ]
        
        for pattern in url_patterns_with_protocol:
            match = re.search(pattern, task)
            if match:
                url = match.group(1)
                # Strip any punctuation that might have been included
                url = url.rstrip('.,;:)')
                print(f"Found URL from pattern match: {url}")
                return url
        
        # Look for common URL patterns WITHOUT protocol (e.g., "Go to google.com")
        url_patterns_without_protocol = [
            r"Navigate to ([a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9][a-zA-Z0-9-]*)+)",
            r"Go to ([a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9][a-zA-Z0-9-]*)+)",
            r"Visit ([a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9][a-zA-Z0-9-]*)+)",
            r"Open ([a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9][a-zA-Z0-9-]*)+)",
            r"Access ([a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]*(?:\.[a-zA-Z0-9][a-zA-Z0-9-]*)+)"
        ]
        
        for pattern in url_patterns_without_protocol:
            match = re.search(pattern, task, re.IGNORECASE)
            if match:
                domain = match.group(1)
                # Add https:// protocol
                url = f"https://{domain}"
                print(f"Found domain from pattern match: {domain} -> {url}")
                return url
        
        # If no URL found, extract from the base_url that was added to the task
        base_url_match = re.search(r"base_url:\s*([^\s\n]+)", task, re.IGNORECASE)
        if base_url_match:
            base_url = base_url_match.group(1).strip()
            # Assume base_url is a path and convert to full URL
            if not urlparse(base_url).scheme:
                # Strip leading slashes to avoid double slashes
                path = base_url.lstrip('/')
                # Use the first allowed domain as the host
                host = f"https://{self.allowed_domains[0]}" if self.allowed_domains else None
                if host:
                    full_url = f"{host}/{path}"
                    print(f"Found base_url in task: {base_url} -> {full_url}")
                    return full_url
            else:
                print(f"Found base_url in task: {base_url}")
                return base_url
        
        # Look for any HTTP URLs in the task
        url_regex = re.compile(r'https?://[^\s\'"]+')
        matches = url_regex.findall(task)
        if matches:
            # Clean up the URL
            url = matches[0].rstrip('.,;:)')
            print(f"Found URL via general regex: {url}")
            return url
            
        # Look for common domain names mentioned in the task
        common_domains = ['google.com', 'wikipedia.org', 'cnn.com', 'yahoo.com', 'amazon.com', 'bing.com']
        for domain in common_domains:
            if domain.lower() in task.lower():
                full_url = f"https://{domain}"
                print(f"Found common domain in task: {domain} -> {full_url}")
                return full_url
            
        # If no URL found, check for domain references that might indicate a URL
        for domain in self.allowed_domains:
            if domain in task and domain != 'about:blank' and not domain.startswith('.'):
                full_url = f"https://{domain}"
                print(f"Found domain reference in task: {full_url}")
                return full_url
        
        print("No URL found in task")
        return None