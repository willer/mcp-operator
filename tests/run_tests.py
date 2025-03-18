#!/usr/bin/env python3
"""
Test runner script for mcp-operator tests.
This script runs unit tests for the core functionality
of the MCP browser operator.
"""

import asyncio
import unittest
import sys
from tests.test_browser_operator import TestBrowserInstance, TestBrowserOperator

class AsyncioTestRunner:
    """Custom test runner that properly handles async test methods."""
    
    def __init__(self, verbosity=2):
        self.verbosity = verbosity
        self.succeeded = 0
        self.failed = 0
        self.failed_tests = []
    
    async def run_test(self, test):
        """Run a single test method."""
        test_method = getattr(test, test._testMethodName)
        print(f"Running {test.__class__.__name__}.{test._testMethodName}...", end=" ")
        
        # Set up test
        try:
            test.setUp()
        except Exception as e:
            print(f"FAILED (setUp error: {e})")
            self.failed += 1
            self.failed_tests.append((test.__class__.__name__, test._testMethodName, f"setUp error: {e}"))
            return
        
        try:
            # Run test method
            if asyncio.iscoroutinefunction(test_method):
                await test_method()
            else:
                test_method()
            print("OK")
            self.succeeded += 1
        except Exception as e:
            print(f"FAILED ({e})")
            self.failed += 1
            self.failed_tests.append((test.__class__.__name__, test._testMethodName, str(e)))
        finally:
            # Clean up
            try:
                test.tearDown()
            except Exception as e:
                print(f"WARNING: tearDown error: {e}")
    
    async def run_suite(self, suite):
        """Run all tests in a suite."""
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                await self.run_suite(test)
            else:
                await self.run_test(test)
                
    async def run(self, test_classes):
        """Run all test classes."""
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        
        for test_class in test_classes:
            suite.addTests(loader.loadTestsFromTestCase(test_class))
        
        # Print header
        print("\nRunning tests:")
        print("-" * 70)
        
        # Count total tests
        total_tests = 0
        for test in suite:
            if isinstance(test, unittest.TestSuite):
                total_tests += test.countTestCases()
            else:
                total_tests += 1
                
        print(f"Found {total_tests} tests to run\n")
        
        # Run all tests
        await self.run_suite(suite)
        
        # Print results
        print("\n" + "=" * 70)
        print(f"RESULTS: {self.succeeded} passed, {self.failed} failed")
        
        if self.failed > 0:
            print("\nFailed tests:")
            for cls_name, method_name, error in self.failed_tests:
                print(f"  {cls_name}.{method_name}: {error}")
            return 1
        else:
            print("\nAll tests passed!")
            return 0

async def run_tests():
    """Run all tests."""
    runner = AsyncioTestRunner(verbosity=2)
    return await runner.run([TestBrowserInstance, TestBrowserOperator])

if __name__ == "__main__":
    # Use asyncio to run the async tests
    sys.exit(asyncio.run(run_tests()))