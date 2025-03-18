# MCP Operator Development Standards

## Development Workflow

### 1. Test-Driven Development
- Always write tests first before implementing features
- Run tests frequently during development
- All PRs must include tests for new functionality

### 2. Testing Commands
```bash
# Run all tests
cd /Users/willer/GitHub/operator-mcp && python -m tests.run_tests

# Run linting
cd /Users/willer/GitHub/operator-mcp && pylint src/

# Run type checking
cd /Users/willer/GitHub/operator-mcp && mypy src/
```

### 3. Code Style Guidelines
- Follow PEP 8 for Python code style
- Use type hints for all function parameters and return values
- Document all classes and methods with docstrings
- Keep functions focused on a single responsibility
- Use meaningful variable and function names

### 4. MCP Operator Best Practices
- Handle all errors gracefully with proper logging
- Computer Use API operations must support multi-step tasks
- Manage memory usage by not storing unnecessary screenshots
- Always include system message in API calls for context
- Test API responses with a variety of inputs

### 5. Browser Automation Guidelines
- Include proper timeouts for all browser operations
- Handle slow-loading websites gracefully
- Ensure screenshots are properly encoded
- Provide meaningful error messages when browser actions fail
- Implement safeguards against navigating to dangerous sites

## Key Components

### Browser Operator
The BrowserOperator class handles interaction with the OpenAI Computer Use API and orchestrates browser automation through Playwright.

### Browser Instance
The BrowserInstance class manages the actual browser state, providing methods for screenshot capture, navigation, etc.

### MCP Server
The server component implements the MCP protocol and exposes the browser tools as MCP tools for LLMs to use.