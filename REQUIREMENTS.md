# MCP Operator Requirements

## Overview
The MCP Operator is a tool that provides browser automation capabilities to LLMs through the MCP (Model Control Protocol) interface. It enables AI models to control a web browser, interact with web pages, and analyze web content.

## Core Components

### Browser Operator
- Manages browser instances through the OpenAI Computer Use API
- Orchestrates browser automation via Playwright
- Handles creation, navigation, and operation of browser instances

### MCP Server
- Implements the MCP protocol for communication with LLMs
- Exposes browser automation tools through a standardized JSON-RPC interface
- Maintains state for browser sessions

## Functional Requirements

### Browser Management
- **Create Browser**: Initialize a new browser instance with persistent state
- **Navigate Browser**: Direct the browser to a specified URL
- **Operate Browser**: Execute natural language instructions for browser interaction
- **Close Browser**: Terminate a browser instance

### Job Management
- **Get Job Status**: Retrieve the status and result of an operation by job ID
- **List Jobs**: View recent browser operation jobs

### Web Interaction
- **Browser Operation**: Ability to follow natural language instructions to interact with web content
- **Project Persistence**: Maintain browser state across sessions with project identifiers

### Additional Playwright Operations
- **Take Screenshot**: Capture the current browser viewport
- **Get Console Logs**: Retrieve browser console output for debugging
- **Get Console Errors**: Capture error messages from the browser console
- **Get Network Logs**: Monitor network activity and request/response data
- **Get Network Errors**: Track failed network requests
- **Scroll To**: Programmatically scroll to specific coordinates on the page
- **Click**: Interact with page elements through mouse clicks
- **Type**: Input text into form fields and other input elements

### Browser Debugging Tools
- **Run Accessibility Audit**: Evaluate page compliance with accessibility standards
- **Run Performance Audit**: Measure page load times and optimization metrics
- **Run SEO Audit**: Analyze page structure for search engine optimization
- **Run NextJS Audit**: Specific auditing for NextJS applications
- **Run Best Practices Audit**: Check adherence to web development best practices
- **Run Debugger Mode**: Advanced debugging interface for troubleshooting
- **Run Audit Mode**: Comprehensive page evaluation for multiple metrics

### User Notes
- **Add Note**: Create and store notes related to browser operations

## Non-functional Requirements

### Performance
- Handle browser operations with appropriate timeouts
- Manage memory usage efficiently, especially for screenshots
- Support concurrent browser instances

### Reliability
- Gracefully handle errors in browser operations
- Provide proper recovery mechanisms for failed operations
- Implement safeguards against navigating to dangerous websites

### Logging
- File-based logging with no console output (to preserve JSON-RPC communication)
- Comprehensive error reporting
- Multiple log levels for different operational needs

### Security
- Session isolation between different browser instances
- Secure handling of web content
- Protection against malicious websites

## Development Standards

### Testing
- Test-driven development approach
- Integration tests with real APIs (no mocks)
- Support for multi-step task testing

### Code Quality
- Type annotations for all functions
- Comprehensive documentation
- Adherence to PEP 8 standards
- Proper error handling
- Modular and maintainable code structure

## Communication Protocol

### JSON-RPC Interface
- Standard MCP protocol compliance
- Clean stdin/stdout channels for communication
- Structured error responses
- Asynchronous job handling with status tracking