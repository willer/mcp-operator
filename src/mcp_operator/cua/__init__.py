"""
OpenAI Computer Use Agent (CUA) integration for web testing.

This package provides classes and utilities for using OpenAI's Computer Use Agent
to automate web testing tasks.
"""

from .computer import AsyncComputer, AsyncPlaywrightComputer, AsyncLocalPlaywrightComputer
from .agent import Agent, create_response
from .utils import process_agent_output, format_task_from_csv_row, get_full_url, load_auth_state, TestStatus

__all__ = [
    'AsyncComputer',
    'AsyncPlaywrightComputer', 
    'AsyncLocalPlaywrightComputer',
    'Agent',
    'create_response',
    'process_agent_output',
    'format_task_from_csv_row',
    'get_full_url',
    'load_auth_state',
    'TestStatus',
]