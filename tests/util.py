import unittest
import sys
import subprocess as sub
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


class TestBase(unittest.TestCase):
    def setUp(self):
        self.maxDiff = sys.maxsize

    def _exec(self, cmd: str) -> str:
        proc: sub.CompletedProcess = sub.run(cmd, shell=True, capture_output=True)
        out = proc.stdout.decode()
        err = proc.stderr.decode()
        self.assertEqual(0, proc.returncode, err)
        return out

    def _assert_tags(self):
        tags = self._exec('git tag').strip()
        if len(tags.split('\n')) < 2:
            self._exec('git tag -am "unit test tag 1" v0.0.1')
            self._exec('git tag -am "unit test tag 2" v0.0.2')

    def _delete_tags(self):
        self._exec('git tag | xargs git tag -d')

    def _restore_tags(self):
        self._delete_tags()
        self._exec('git pull --tags')
