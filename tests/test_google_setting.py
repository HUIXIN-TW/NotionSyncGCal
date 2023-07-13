import unittest
import os
import sys

# Add the parent directory to PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.Token import Google

# TODO: Implement setUp and tearDown methods (load JSON file)


class GoogleSettingTest(unittest.TestCase):
    def test_google_setUp(self):
        # Test is incomplete
        self.fail("Test has not been implemented yet. Incomplete.")

    # TODO: Implement additional test methods


# Running the tests
if __name__ == "__main__":
    unittest.main()
