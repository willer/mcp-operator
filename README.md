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

#### Browser Automation (Asynchronous/Job-based)
The browser automation tools use an asynchronous job-based approach to prevent client timeouts during long-running operations.

- create-browser: Creates a new browser instance
  - Takes "project_name" as a required string argument (used for browser state identification and persistence)
  - Returns a job_id for tracking the operation's progress
  - When complete, provides confirmation message and initial screenshot
  - Browser state (cookies, storage, etc.) is automatically saved between sessions based on project name

- navigate-browser: Navigates to a URL in the browser
  - Takes "project_name" and "url" as required string arguments
  - Returns a job_id for tracking the operation's progress
  - When complete, provides navigation result and current page screenshot

- operate-browser: Operates the browser based on natural language instructions
  - Takes "project_name" and "instruction" as required string arguments
  - Returns a job_id for tracking the operation's progress
  - Uses OpenAI's Computer Use API to interpret and interact with the current page
  - Supports a wide range of actions: click, type, scroll, drag, keypress, etc.
  - Handles multi-step operations through continuous action execution until task completion
  - Enhanced context awareness for better page interaction decision-making
  - Built-in stuck detection and recovery to handle repetitive action loops
  - Provides detailed page element analysis for improved task completion
  - When complete, provides execution results and updated page screenshot

- close-browser: Closes a browser instance
  - Takes "project_name" as a required string argument
  - Returns a job_id for tracking the operation's progress
  - When complete, provides confirmation message

#### Job Management
- get-job-status: Checks the status of a browser operation job
  - Takes "job_id" as a required string argument
  - Returns job details including status, creation time, and results when complete
  - For completed jobs with screenshots, includes the screenshot in the response

- list-jobs: Lists recent browser operation jobs
  - Optional "limit" parameter to control how many jobs to return (default: 10)
  - Returns a list of job summaries sorted by most recent first

#### Asynchronous Workflow Pattern
When using the browser automation tools with AI assistants, follow this pattern:

1. **Start Operation**:
   ```
   // Example with operate-browser tool
   result = operate-browser(project_name="amazon-shopping", instruction="Search for dinner plates on Amazon")
   // Tool returns immediately with a job_id
   job_id = extract_job_id_from(result)
   ```

2. **Poll for Completion**:
   ```
   // Check status until complete
   status = get-job-status(job_id=job_id)
   while status is not "completed":
     wait brief period
     status = get-job-status(job_id=job_id)
   ```

3. **Process Results**:
   ```
   // When job completes, process the results
   final_result = get-job-status(job_id=job_id)
   // final_result will contain text output and screenshots
   ```

This approach prevents client timeouts while allowing complex, long-running browser operations to complete.

## Persistent Browser State

The MCP Operator supports persistent browser state when creating browsers with a project name:

### How It Works

1. Create a browser with a meaningful project name:
   ```
   create-browser(project_name="amazon-shopping")
   ```

2. The browser state (cookies, local storage, session storage) is automatically:
   - Loaded from disk if a previous session with the same project name exists
   - Saved to disk after navigation and significant interactions
   - Preserved between sessions, even if you close and later restart the application

3. Multiple projects can maintain independent browser states:
   ```
   create-browser(project_name="shopping-project")
   create-browser(project_name="research-project")
   ```

4. State files are stored in a temporary directory using a hash of the project name

### Benefits

- Maintain login sessions across browser restarts
- Continue multi-step workflows from where they left off
- Store shopping carts, preferences, and other personalized state
- Simulate real user behavior with persistent browsing history

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

## Multi-Step Operation Improvements

The MCP operator has been enhanced with significant improvements to handle multi-step browser operations more effectively:

### Key Improvements

1. **Enhanced Initial Prompting**:
   - Clearer, more direct system messages for the Computer Use API
   - More structured instructions with explicit action requirements
   - Emphasis on using direct navigation with full URLs

2. **Stuck Detection and Resolution**:
   - Automatic detection of repetitive clicking patterns
   - Alternative action suggestions when stuck is detected
   - Detailed page analysis to provide better context for decisions

3. **Detailed Page Element Analysis**:
   - Identification of key UI elements with coordinates (search bars, buttons, forms)
   - Detection of page type (homepage, search results, product page, etc.)
   - Visibility testing to ensure elements are present in viewport

4. **Robust Navigation Handling**:
   - Enhanced URL validation and automatic protocol addition
   - Multi-stage navigation with appropriate timeouts
   - Fallback strategies for navigation failures
   - Verification of page loading state

5. **Better Continuation Messages**:
   - More context about previous actions and current page state
   - Clear, focused instructions for the next action
   - Presentation of clickable elements with their coordinates

These improvements significantly enhance the ability of the system to complete complex multi-step tasks without getting stuck in repetitive action loops.

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