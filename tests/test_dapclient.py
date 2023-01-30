"""Test dapclient namespace."""

import unittest

import dapclient


class TestNamespace(unittest.TestCase):

    """Test dapclient namespace."""

    def test_namespace(self):
        """Test the namespace."""
        self.assertEqual(dapclient.__name__, "dapclient")
