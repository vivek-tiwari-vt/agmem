"""Run new feature tests without pytest (unittest only)."""

import sys
import unittest

# Add project root to path
sys.path.insert(0, str(__file__).rsplit("/", 1)[0].rsplit("/", 1)[0])

loader = unittest.TestLoader()
suite = unittest.TestSuite()
suite.addTests(loader.loadTestsFromName("tests.test_access_index"))
suite.addTests(loader.loadTestsFromName("tests.test_temporal_index"))
suite.addTests(loader.loadTestsFromName("tests.test_retrieval"))
suite.addTests(loader.loadTestsFromName("tests.test_commit_importance"))
suite.addTests(loader.loadTestsFromName("tests.test_consistency"))
suite.addTests(loader.loadTestsFromName("tests.test_decay"))
suite.addTests(loader.loadTestsFromName("tests.test_advanced_commands"))

runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
