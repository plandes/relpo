from typing import Tuple
from datetime import date
import copy
from pathlib import Path
from zensols.relpo import Version, ChangeLogEntry, ChangeLog
from zensols.relpo.project import Project
from util import TestBase


class TestVersion(TestBase):
    def test_cmp(self):
        vstr = Version()
        self.assertEqual('v0.0.1', str(vstr))
        ver = Version.from_str('v1.2.3')
        self.assertEqual(1, ver.major)
        self.assertEqual(2, ver.minor)
        self.assertEqual(3, ver.debug)
        ver = Version.from_str('1.2.3')
        self.assertEqual(1, ver.major)
        self.assertEqual(2, ver.minor)
        self.assertEqual(3, ver.debug)
        ver.increment()
        self.assertEqual(1, ver.major)
        self.assertEqual(2, ver.minor)
        self.assertEqual(4, ver.debug)
        ver2 = copy.deepcopy(ver)
        self.assertTrue(ver == ver2)
        ver2.increment('major')
        self.assertTrue(ver != ver2)
        self.assertEqual('v2.2.4', str(ver2))
        self.assertTrue(ver < ver2)
        self.assertTrue(ver2 > ver)

        self.assertTrue(Version.from_str('v1.2.3') < Version.from_str('v2.2.3'))
        self.assertTrue(Version.from_str('v1.2.3') < Version.from_str('v1.3.3'))
        self.assertTrue(Version.from_str('v1.2.3') < Version.from_str('v1.2.4'))

        self.assertTrue(Version.from_str('v1.2.3') <= Version.from_str('v1.2.3'))
        self.assertTrue(Version.from_str('v1.2.3') <= Version.from_str('v2.2.3'))
        self.assertTrue(Version.from_str('v1.2.3') <= Version.from_str('v1.3.3'))
        self.assertTrue(Version.from_str('v1.2.3') <= Version.from_str('v1.2.4'))

        self.assertTrue(Version.from_str('v2.2.3') > Version.from_str('v1.2.3'))
        self.assertTrue(Version.from_str('v1.3.3') > Version.from_str('v1.2.3'))
        self.assertTrue(Version.from_str('v1.2.4') > Version.from_str('v1.2.3'))

        self.assertTrue(Version.from_str('v1.2.3') >= Version.from_str('v1.2.3'))
        self.assertTrue(Version.from_str('v2.2.3') >= Version.from_str('v1.2.3'))
        self.assertTrue(Version.from_str('v1.3.3') >= Version.from_str('v1.2.3'))
        self.assertTrue(Version.from_str('v1.2.4') >= Version.from_str('v1.2.3'))

    def test_sort(self):
        v1 = Version.from_str('v0.0.6')
        v2 = Version.from_str('v1.0.0')
        self.assertEqual('v0.0.6', str(v1))
        self.assertEqual('v1.0.0', str(v2))
        self.assertTrue(v1 < v2)
        self.assertTrue(v2 > v1)
        vers = [v2, v1]
        vers = list(sorted(vers))
        self.assertTrue(vers[0] == v1)
        self.assertTrue(vers[1] == v2)
        vers = [v1, v2]
        vers = list(sorted(vers))
        self.assertTrue(vers[0] == v1)
        self.assertTrue(vers[1] == v2)


class TestChangeLog(TestBase):
    def test_change(self):
        ch = ChangeLog(Path('test-resources/changelog-1.md'))
        entries: Tuple[ChangeLogEntry, ...] = tuple(ch.entries)
        self.assertEqual(2, len(entries))
        e1: ChangeLogEntry = entries[0]
        self.assertEqual(Version, type(e1.version))
        self.assertEqual(date, type(e1.date))
        self.assertEqual('2025-04-05', str(e1.date))
        self.assertEqual('2025-04-10', str(entries[1].date))


class TestProject(TestBase):
    def setUp(self):
        self.project = Project(
            (Path('test-resources/relpo.yml'),), Path('target'))


class TestProjectSerialize(TestProject):
    def test_repo_serialize(self):
        self.assertTrue(len(self.project.repo.asjson()) > 10)

    def test_serialize(self):
        self.assertTrue(len(self.project.asjson()) > 10)


class TestProjectTag(TestProject):
    def setUp(self):
        super().setUp()
        self._delete_tags()

    def tearDown(self):
        self._restore_tags()

    def test_tag_text(self):
        self._assert_tags()
        ver = self.project.repo.tags[-1].version
        self.assertEqual(Version, type(ver))
        self.assertTrue(ver.name.startswith('v0.0'))

    def test_tag_order(self):
        self._assert_tags()
        entries = self.project.repo.tags
        first = entries[0]
        last = entries[-1]
        self.assertTrue(first.version < last.version)
