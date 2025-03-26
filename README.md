# MCP Browser Operator

A Model Control Protocol (MCP) server for browser automation that enables LLMs to control a web browser, interact with web pages, and analyze web content through a standardized JSON-RPC interface.

## Features

- **Browser Management**: Create, navigate, operate, and close browser instances
- **Job Management**: Track status of browser operations with job IDs
- **Web Interaction**: Execute natural language instructions using OpenAI's Computer Use API
- **Browser Tools**: Access console logs, network activity, screenshots, and more
- **Auditing**: Run accessibility, performance, SEO, and other web page audits

## Requirements

- Python 3.11+
- Playwright
- OpenAI API key (for the Computer Use API)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/operator-mcp.git
   cd operator-mcp
   ```

2. Install dependencies:
   ```
   pip install -e .
   ```

3. Install Playwright browsers:
   ```
   playwright install chromium
   ```

4. Set your OpenAI API key:
   ```
   export OPENAI_API_KEY=your-api-key
   ```

## Usage

Start the MCP server:

```
python run_mcp_server.py
```

The server listens for JSON-RPC requests on stdin and responds on stdout, following the MCP protocol.

### Core Methods

#### Browser Management

- **Create Browser**: Initialize a new browser instance
  ```json
  {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "mcp__browser-operator__create-browser",
    "params": {
      "project_name": "my-project"
    }
  }
  ```

- **Navigate Browser**: Direct the browser to a specified URL
  ```json
  {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "mcp__browser-operator__navigate-browser",
    "params": {
      "project_name": "my-project",
      "url": "https://example.com"
    }
  }
  ```

- **Operate Browser**: Execute natural language instructions for browser interaction
  ```json
  {
    "jsonrpc": "2.0",
    "id": 3,
    "method": "mcp__browser-operator__operate-browser",
    "params": {
      "project_name": "my-project",
      "instruction": "Find the heading on this page and tell me what it says."
    }
  }
  ```

- **Close Browser**: Terminate a browser instance
  ```json
  {
    "jsonrpc": "2.0",
    "id": 4,
    "method": "mcp__browser-operator__close-browser",
    "params": {
      "project_name": "my-project"
    }
  }
  ```

#### Job Management

- **Get Job Status**: Retrieve the status and result of an operation by job ID
  ```json
  {
    "jsonrpc": "2.0",
    "id": 5,
    "method": "mcp__browser-operator__get-job-status",
    "params": {
      "job_id": "job-12345"
    }
  }
  ```

- **List Jobs**: View recent browser operation jobs
  ```json
  {
    "jsonrpc": "2.0",
    "id": 6,
    "method": "mcp__browser-operator__list-jobs",
    "params": {
      "limit": 10
    }
  }
  ```

#### User Notes

- **Add Note**: Create and store notes related to browser operations
  ```json
  {
    "jsonrpc": "2.0",
    "id": 7,
    "method": "mcp__browser-operator__add-note",
    "params": {
      "name": "My Note",
      "content": "Important information about this browser session"
    }
  }
  ```

### Additional Methods

#### Browser Debugging Tools

- **Get Console Logs**: `mcp__browser-tools__getConsoleLogs`
- **Get Console Errors**: `mcp__browser-tools__getConsoleErrors`
- **Get Network Logs**: `mcp__browser-tools__getNetworkLogs`
- **Get Network Errors**: `mcp__browser-tools__getNetworkErrors`
- **Take Screenshot**: `mcp__browser-tools__takeScreenshot`
- **Get Selected Element**: `mcp__browser-tools__getSelectedElement`
- **Wipe Logs**: `mcp__browser-tools__wipeLogs`

#### Audit Tools

- **Run Accessibility Audit**: `mcp__browser-tools__runAccessibilityAudit`
- **Run Performance Audit**: `mcp__browser-tools__runPerformanceAudit`
- **Run SEO Audit**: `mcp__browser-tools__runSEOAudit`
- **Run NextJS Audit**: `mcp__browser-tools__runNextJSAudit`
- **Run Best Practices Audit**: `mcp__browser-tools__runBestPracticesAudit`
- **Run Debugger Mode**: `mcp__browser-tools__runDebuggerMode`
- **Run Audit Mode**: `mcp__browser-tools__runAuditMode`

## Asynchronous Workflow Pattern

Browser operations are asynchronous and use a job-based approach:

1. **Start Operation**: Call a browser method which returns a job_id
2. **Poll for Completion**: Use get-job-status until job is completed
3. **Process Results**: When job completes, access results from the job status

This approach prevents client timeouts while allowing complex browser operations to complete.

## Persistent Browser State

The MCP Operator maintains persistent state when browsers are created with a project name:

- Browser state (cookies, local storage, session storage) is preserved between sessions
- Multiple projects can maintain independent browser states
- Useful for maintaining login sessions, shopping carts, or other personalized state

## Project Structure

- `src/mcp_operator/`: Main package
  - `__init__.py`: Package initialization
  - `__main__.py`: Entry point for package
  - `server.py`: MCP server implementation
  - `browser.py`: Browser operator implementation
  - `cua/`: Computer Use API components
    - `agent.py`: Agent implementation
    - `computer.py`: Computer interface
    - `utils.py`: Utility functions
- `run_mcp_server.py`: Script to run the MCP server

## Development

### Using MCP Inspector

For debugging, use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector python run_mcp_server.py
```

This provides a web interface to test your MCP server.

## Security

- Domain blocking for potentially harmful sites
- URL validation before navigation
- Session isolation between different browser instances
- File-based logging (no stdout to preserve MCP protocol)