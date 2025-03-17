# Browser Operator MCP

This is an implementation of OpenAI's Operator as a Claude MCP. It uses Playwright to manage browser instances and allows Claude to interact with the browser on your behalf.

## Features

- Launch and control browser instances with Playwright
- Take screenshots of the current browser state
- Execute browser actions like navigating, clicking, typing, and waiting
- Persist browser sessions across multiple interactions
- Option to take over the session manually for tasks like logging in

## Requirements

- Python 3.8+
- OpenAI API key (set as environment variable `OPENAI_API_KEY`)
- uvx tool for running the MCP

## Installation

### Installing from GitHub

You can install this MCP directly from GitHub:

```bash
uvx add github:willer/mcp-operator
```

The MCP will automatically install its dependencies when run via uvx.

## Usage

### Starting the MCP with uvx

After installation:

```bash
uvx run mcp-operator
```

Or, you can run it directly from the repository URL without installing:

```bash
uvx run github:willer/mcp-operator
```

### Using with Claude

Once the MCP is running, you can use it with MCP clients such as Claude Code and Claude Desktop. Here are some example prompts:

- "Go to https://example.com and click the login button"
- "Fill in the search box with 'Claude AI' and press Enter"
- "Extract information from this webpage about pricing"

Claude will:
1. Capture the current state of the web page
2. Determine what actions to take based on your request
3. Execute those actions in the browser
4. Report back what it did and show the new state

### Browser ID

The MCP generates a unique ID for each browser session. You can use this ID to continue working with the same browser instance in future interactions. The ID will be included in responses from the MCP.

### Manual Intervention

For tasks that require manual intervention (like logging in):

1. Claude will open the browser to the login page
2. You can take over the browser manually to enter credentials
3. Tell Claude when you're done, and it can continue automation

## Security Notes

- Your OpenAI API key is required for the computer vision capabilities
- No passwords or sensitive data should be shared with Claude
- Always manually handle login processes and sensitive data entry

## Troubleshooting

- If the browser doesn't launch, check that Playwright is installed correctly
- If actions fail, try being more specific in your instructions to Claude
- For OpenAI API errors, verify your API key is set correctly

## License

This project is open source and available under the MIT License.
