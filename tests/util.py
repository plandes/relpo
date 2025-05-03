import unittest
import sys
from unittest.case import _common_shorten_repr
import difflib


def assertMultiLineEqual(self, first, second, msg=None):
    """Assert that two multi-line strings are equal."""
    self.assertIsInstance(first, str, 'First argument is not a string')
    self.assertIsInstance(second, str, 'Second argument is not a string')

    if first != second:
        firstlines = first.splitlines(keepends=True)
        secondlines = second.splitlines(keepends=True)
        if len(firstlines) == 1 and first.strip('\r\n') == first:
            firstlines = [first + '\n']
            secondlines = [second + '\n']
        standardMsg = '%s != %s' % _common_shorten_repr(first, second)
        diff = '\n' + ''.join(difflib.unified_diff(firstlines, secondlines))
        standardMsg = self._truncateMessage(standardMsg, diff)
        self.fail(self._formatMessage(msg, standardMsg))


# replace inherited method used by framework
unittest.TestCase.assertMultiLineEqual = assertMultiLineEqual


class TestMultiline(unittest.TestCase):
    def setUp(self):
        self.maxDiff = sys.maxsize
