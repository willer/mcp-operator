# mcp-operator MCP server

A web browser operator MCP server project that allows AI assistants to control a Chrome browser.

## Components

### Resources

The server implements a simple note storage system with:
- Custom note:// URI scheme for accessing individual notes
- Each note resource has a name, description and text/plain mimetype

### Prompts

The server provides a single prompt:
- summarize-notes: Creates summaries of all stored notes
  - Optional "style" argument to control detail level (brief/detailed)
  - Generates prompt combining all current notes with style preference

### Tools

The server implements the following tools:

#### Note Management
- add-note: Adds a new note to the server
  - Takes "name" and "content" as required string arguments
  - Updates server state and notifies clients of resource changes

#### Browser Automation
- create-browser: Creates a new browser instance
  - Takes "browser_id" as a required string argument
  - Returns a confirmation message and initial screenshot

- navigate-browser: Navigates to a URL in the browser
  - Takes "browser_id" and "url" as required string arguments
  - Returns navigation result and current page screenshot

- operate-browser: Operates the browser based on natural language instructions
  - Takes "browser_id" and "instruction" as required string arguments
  - Uses OpenAI's Computer Use API to interpret and interact with the current page
  - Supports a wide range of actions: click, type, scroll, drag, keypress, etc.
  - Returns execution results and updated page screenshot

- close-browser: Closes a browser instance
  - Takes "browser_id" as a required string argument
  - Returns a confirmation message

## Configuration

To use the browser automation tools, you need to:

1. Install the necessary dependencies:
   - Python 3.11 or higher
   - Playwright for browser automation
   - An OpenAI API key with access to the Computer Use API

2. Set up your environment:
   - Create a `.env` file or set environment variables:
     ```
     OPENAI_API_KEY=your-api-key-here
     # Optional: If you have an org ID
     # OPENAI_ORG=your-org-id
     ```
   - Install browser dependencies for Playwright with `playwright install chromium`

## Quickstart

### Install

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  ```
  "mcpServers": {
    "mcp-operator": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/willer/GitHub/operator-mcp/mcp-operator",
        "run",
        "mcp-operator"
      ]
    }
  }
  ```
</details>

<details>
  <summary>Published Servers Configuration</summary>
  ```
  "mcpServers": {
    "mcp-operator": {
      "command": "uvx",
      "args": [
        "mcp-operator"
      ]
    }
  }
  ```
</details>

## Development

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

3. Publish to PyPI:
```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags:
- Token: `--token` or `UV_PUBLISH_TOKEN`
- Or username/password: `--username`/`UV_PUBLISH_USERNAME` and `--password`/`UV_PUBLISH_PASSWORD`

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).


You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /Users/willer/GitHub/operator-mcp/mcp-operator run mcp-operator
```


Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.