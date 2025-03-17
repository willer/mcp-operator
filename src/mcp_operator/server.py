import asyncio
import base64

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio

from .browser import BrowserOperator

# Store notes as a simple key-value dict to demonstrate state management
notes: dict[str, str] = {}
# Initialize browser operator
browser_operators: dict[str, BrowserOperator] = {}

server = Server("mcp-operator")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available note resources.
    Each note is exposed as a resource with a custom note:// URI scheme.
    """
    return [
        types.Resource(
            uri=AnyUrl(f"note://internal/{name}"),
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific note's content by its URI.
    The note name is extracted from the URI host component.
    """
    if uri.scheme != "note":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    name = uri.path
    if name is not None:
        name = name.lstrip("/")
        return notes[name]
    raise ValueError(f"Note not found: {name}")

@server.list_prompts()
async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    Each prompt can have optional arguments to customize its behavior.
    """
    return [
        types.Prompt(
            name="summarize-notes",
            description="Creates a summary of all notes",
            arguments=[
                types.PromptArgument(
                    name="style",
                    description="Style of the summary (brief/detailed)",
                    required=False,
                )
            ],
        )
    ]

@server.get_prompt()
async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate a prompt by combining arguments with server state.
    The prompt includes all current notes and can be customized via arguments.
    """
    if name != "summarize-notes":
        raise ValueError(f"Unknown prompt: {name}")

    style = (arguments or {}).get("style", "brief")
    detail_prompt = " Give extensive details." if style == "detailed" else ""

    return types.GetPromptResult(
        description="Summarize the current notes",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n"
                    + "\n".join(
                        f"- {name}: {content}"
                        for name, content in notes.items()
                    ),
                ),
            )
        ],
    )

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        ),
        types.Tool(
            name="create-browser",
            description="Create a new browser instance",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                },
                "required": ["browser_id"],
            },
        ),
        types.Tool(
            name="navigate-browser",
            description="Navigate to a URL in the browser",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                    "url": {"type": "string"},
                },
                "required": ["browser_id", "url"],
            },
        ),
        types.Tool(
            name="operate-browser",
            description="Operate the browser based on a natural language instruction",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                    "instruction": {"type": "string"},
                },
                "required": ["browser_id", "instruction"],
            },
        ),
        types.Tool(
            name="close-browser",
            description="Close a browser instance",
            inputSchema={
                "type": "object",
                "properties": {
                    "browser_id": {"type": "string"},
                },
                "required": ["browser_id"],
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    if not arguments:
        raise ValueError("Missing arguments")

    if name == "add-note":
        note_name = arguments.get("name")
        content = arguments.get("content")

        if not note_name or not content:
            raise ValueError("Missing name or content")

        # Update server state
        notes[note_name] = content

        # Notify clients that resources have changed
        await server.request_context.session.send_resource_list_changed()

        return [
            types.TextContent(
                type="text",
                text=f"Added note '{note_name}' with content: {content}",
            )
        ]
    
    elif name == "create-browser":
        browser_id = arguments.get("browser_id")
        if not browser_id:
            raise ValueError("Missing browser_id")
        
        # Create a new browser operator
        browser_operator = BrowserOperator(browser_id)
        await browser_operator.initialize()
        browser_operators[browser_id] = browser_operator
        
        # Take initial screenshot to show
        screenshot = await browser_operator.browser_instance.take_screenshot()
        
        return [
            types.TextContent(
                type="text",
                text=f"Created browser with ID: {browser_id}",
            ),
            types.ImageContent(
                type="image",
                data=f"data:image/png;base64,{screenshot}",
            ) if screenshot else types.TextContent(
                type="text",
                text="Could not take initial screenshot.",
            )
        ]
    
    elif name == "navigate-browser":
        browser_id = arguments.get("browser_id")
        url = arguments.get("url")
        
        if not browser_id or not url:
            raise ValueError("Missing browser_id or url")
        
        if browser_id not in browser_operators:
            raise ValueError(f"Browser with ID {browser_id} not found")
        
        browser_operator = browser_operators[browser_id]
        result = await browser_operator.browser_instance.navigate(url)
        screenshot = await browser_operator.browser_instance.take_screenshot()
        
        return [
            types.TextContent(
                type="text",
                text=result,
            ),
            types.ImageContent(
                type="image",
                data=f"data:image/png;base64,{screenshot}",
            ) if screenshot else types.TextContent(
                type="text",
                text="Could not take screenshot after navigation.",
            )
        ]
    
    elif name == "operate-browser":
        browser_id = arguments.get("browser_id")
        instruction = arguments.get("instruction")
        
        if not browser_id or not instruction:
            raise ValueError("Missing browser_id or instruction")
        
        if browser_id not in browser_operators:
            raise ValueError(f"Browser with ID {browser_id} not found")
        
        browser_operator = browser_operators[browser_id]
        result = await browser_operator.process_message(instruction)
        
        responses = [
            types.TextContent(
                type="text",
                text=result["text"],
            )
        ]
        
        if "screenshot" in result and result["screenshot"]:
            responses.append(
                types.ImageContent(
                    type="image",
                    data=f"data:image/png;base64,{result['screenshot']}",
                )
            )
        
        return responses
    
    elif name == "close-browser":
        browser_id = arguments.get("browser_id")
        
        if not browser_id:
            raise ValueError("Missing browser_id")
        
        if browser_id not in browser_operators:
            raise ValueError(f"Browser with ID {browser_id} not found")
        
        browser_operator = browser_operators.pop(browser_id)
        await browser_operator.close()
        
        return [
            types.TextContent(
                type="text",
                text=f"Closed browser with ID: {browser_id}",
            )
        ]
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="mcp-operator",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )