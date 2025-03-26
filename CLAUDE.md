# MCP-Operator Development Guide

## Commands
- Install: `pip install -e .`
- Setup: `playwright install chromium`
- Run server: `./run-server [--log-dir /path/to/logs] [--debug]`
- Run all tests: `./run-tests`
- Run specific test: `./run-tests --test TestBrowserOperatorMethods`
- Test types: `./run-tests --unit-only` or `./run-tests --integration-only`
- Test harness: `./run-test-harness`

## Code Style
- **Imports**: Standard modules ’ Third-party ’ Local; import specific classes
- **Types**: Use type hints throughout with typing module (Dict, Optional, etc.)
- **Naming**: PascalCase for classes, snake_case for methods/variables, UPPER_SNAKE_CASE for constants
- **Error Handling**: Specific exception handling with proper cleanup, especially for browser resources
- **Async**: Use asyncio consistently with async context managers for resource cleanup
- **Docstrings**: Google-style format with Args sections and type annotations
- **Logging**: File-based only (no stdout to preserve MCP protocol)
- **Tests**: Separate unit/integration tests; mock objects for unit tests

Keep code modular with clear separation of concerns. Prioritize simplicity and delete deprecated code.