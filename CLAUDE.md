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

# Run real multi-step tests
cd /Users/willer/GitHub/operator-mcp && ./run_real_multistep.sh --task=search
```

### 3. Environment Setup
- Using virtual environments with venv
- Using uv for package management
- Always activate the environment before development:
  ```bash
  cd /Users/willer/GitHub/operator-mcp
  source .venv/bin/activate  # Or appropriate activation command
  ```

### 4. Code Style Guidelines
- Follow PEP 8 for Python code style
- Use type hints for all function parameters and return values
- Document all classes and methods with docstrings
- Keep functions focused on a single responsibility
- Use meaningful variable and function names
- NEVER use print() statements in production code - always use the logging module
- Remember that print() statements will break the JSON-RPC protocol in MCP tools

### 5. Testing Rules
- No mocks for integration tests - use real APIs
- No cheating or workarounds in tests
- Use reasonable defaults for functions and scripts
- DO NOT add instructive text that tells the AI how to use websites in prompts
- No step-by-step guides for the AI in tests or code
- Let the AI figure out how to complete tasks using the general system message

### 6. MCP Operator Best Practices
- Handle all errors gracefully with proper logging
- Computer Use API operations must support multi-step tasks
- Manage memory usage by not storing unnecessary screenshots
- Always include system message in API calls for context
- Test API responses with a variety of inputs
- Set up the logger at the module level with:
  ```python
  import logging
  logger = logging.getLogger('mcp-operator')
  ```
- Use appropriate log levels:
  ```python
  logger.debug("Fine-grained diagnostic information")
  logger.info("Normal operation messages")
  logger.warning("Concerning but non-critical issues")
  logger.error("Errors that prevent functionality")
  logger.critical("System-wide failures")
  ```

### 7. Browser Automation Guidelines
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

## MCP Server Development Guidelines

1. **JSON-RPC Communication**
   - NEVER write directly to stdout or stderr as this will break the JSON-RPC protocol
   - All logging must go to a file, NEVER to console
   - The MCP protocol uses stdin/stdout for communication - keep these channels clean

2. **Logging Setup**
   - Always configure logging to file only:
   ```python
   # Set up file-only logging
   log_dir = os.path.join(os.path.expanduser("~"), ".mcp-operator-logs")
   os.makedirs(log_dir, exist_ok=True)
   log_file = os.path.join(log_dir, "mcp-operator.log")
   
   logging.basicConfig(
       level=logging.INFO,
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       handlers=[
           logging.FileHandler(log_file),
       ]
   )
   
   # Remove any handlers that might log to console
   for handler in logging.root.handlers[:]:
       if isinstance(handler, logging.StreamHandler):
           logging.root.removeHandler(handler)
   
   # Create module logger
   logger = logging.getLogger('mcp-operator')
   ```

3. **Debugging**
   - Check the log file at ~/.mcp-operator-logs/mcp-operator.log
   - Never add print statements for debugging - use logger.debug() instead