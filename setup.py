#!/usr/bin/env python3
from setuptools import setup, find_packages

setup(
    name="mcp-operator",
    version="0.1.0",
    description="Browser Operator MCP using Playwright for Claude",
    author="Claude",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "fastapi>=0.95.0",
        "uvicorn>=0.21.0",
        "aiohttp>=3.8.4",
        "playwright>=1.30.0",
        "pydantic>=1.10.7"
    ],
    python_requires=">=3.8",
)