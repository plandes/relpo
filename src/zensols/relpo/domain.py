"""Application domain classes.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import Dict, List, Tuple, Any, Optional, Type, ClassVar
from dataclasses import dataclass, field
import dataclasses
import logging
import re
import json
import yaml
from io import StringIO
from pathlib import Path
from datetime import datetime
from datetime import date as Date

logger = logging.getLogger(__name__)


class ProjectRepoError(Exception):
    pass


class Dumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(Dumper, self).increase_indent(flow, False)


@dataclass
class Flattenable(object):
    """A class that that generates a dictionary recursively from data classes
    and primitive data structures.

    """
    def asdict(self) -> Dict[str, Any]:
        """Serialize the object data into a flat dictionary recursively."""
        return dataclasses.asdict(self)

    def asjson(self, **kwargs) -> str:
        """Return build information in JSON format."""
        writer = StringIO()
        json.dump(self.asdict(), writer, **kwargs)
        return writer.getvalue()

    def asyaml(self) -> str:
        writer = StringIO()
        yaml.dump(
            self.asdict(),
            stream=writer,
            Dumper=Dumper,
            default_flow_style=False)
        return writer.getvalue()


@dataclass(order=True, unsafe_hash=True)
class Version(Flattenable):
    """A container class for a tag version.  All tags have an implicit format by
    sorting in decimal format (i.e. ``<major>.<minor>.<version>``).  This class
    contains methods that make it sortable.

    """
    major: int = field(default=0)
    minor: int = field(default=0)
    debug: int = field(default=1)

    @staticmethod
    def from_str(s: str) -> Version:
        """Create a version instance from a string formatted version.

        :return: a new instance of ``Version``

        """
        m = re.search(r'^v?(\d+)\.(\d+)\.(\d+)$', s)
        if m is not None:
            return Version(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    def _format(self, prefix: str = 'v') -> str:
        """Return a formatted string version of the instance.

        """
        return prefix + '{major}.{minor}.{debug}'.format(**self.__dict__)

    @property
    def name(self) -> str:
        """The name of the version, which as a ``v`` prepended followed by the
        numerical (:obj:`simple`) version.

        """
        if not hasattr(self, '_name'):
            self._name = self._format()
        return self._name

    @property
    def simple(self) -> str:
        """The `simple`_ decimal version, which has the form::

            (i.e. ``<major>.<minor>.<version>``)

        .. _simple: https://packaging.python.org/en/latest/discussions/versioning/

        """
        if not hasattr(self, '_simple'):
            self._simple = self._format(prefix='')
        return self._simple

    def increment(self, decimal: str = 'debug', inc: int = 1):
        """Increment the version in the instance.  By default the debug portion
        of the instance is incremented.

        """
        if decimal == 'major':
            self.major += inc
        elif decimal == 'minor':
            self.minor += inc
        elif decimal == 'debug':
            self.debug += inc
        else:
            raise ValueError(f'uknown decimal type: {decimal}')

    def asdict(self) -> Dict[str, Any]:
        dct = super().asdict()
        dct['name'] = str(self)
        return dct

    def __str__(self):
        return self.name


@dataclass
class Entry(Flattenable):
    """Base class for things that have versions with dates.

    """
    version: Version = field()
    """The version of the entry."""

    date: Date = field()
    """The date the entry was created."""

    @property
    def is_today(self) -> bool:
        """Whether the log as created today."""
        today = datetime.now().date()
        return today == self.date

    def asdict(self) -> Dict[str, Any]:
        dct = super().asdict()
        dct['version'] = self.version.simple
        dct['date'] = dct['date'].isoformat()
        return dct

    def __str__(self) -> str:
        return f'{self.version} [{self.date}]'


@dataclass
class Tag(Entry):
    """A git tag that was used for a previous release or a current release.

    """
    name: str = field()
    """The name of the tag."""

    sha: str = field()
    """Unique SHA1 string of the commit."""

    message: str = field()
    """The comment given at tag creation."""

    def asdict(self) -> Dict[str, Any]:
        dct = super().asdict()
        dct.pop('name')
        return dct

    def __str__(self) -> str:
        return f'{super().__str__()} ({self.message})'


@dataclass
class Commit(Flattenable):
    """A Git commit.

    """
    date: Date = field()
    """The date the commit was created."""

    author: str = field()
    """The author of the commit."""

    sha: str = field()
    """Unique SHA1 string of the commit."""

    summary: str = field()
    """The summary comment."""

    def asdict(self) -> Dict[str, Any]:
        dct = super().asdict()
        dct['date'] = self.date.isoformat()
        return dct


@dataclass
class ChangeLogEntry(Entry):
    """A ChangeLog entry.

    """
    _DATE_FORMAT: ClassVar[str] = '%Y-%m-%d'
    _ENTRY_REGEX: ClassVar[re.Pattern] = re.compile(
        r'^## \[(.+)\] - ([0-9-]+)$')

    @classmethod
    def from_str(cls: Type, s: str) -> Optional[ChangeLogEntry]:
        m: re.Match = cls._ENTRY_REGEX.match(s)
        if m is not None:
            ver, date = m.groups()
            return cls(Version.from_str(ver), cls.str2date(date))

    @classmethod
    def str2date(cls: Type, date: str) -> Date:
        return datetime.strptime(date, cls._DATE_FORMAT).date()


@dataclass
class ChangeLog(Flattenable):
    """Parses the `keepchangelog`_ ``CHANGELOG.md`` (markdown) format.

    .. _keepchangelog: http://keepachangelog.com

    """
    path: Path = field()
    """The path to the change log markdown formatted file."""

    @property
    def entries(self) -> Tuple[ChangeLogEntry, ...]:
        if not hasattr(self, '_entries'):
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"parsing '{self.path}'")
            with open(self.path) as f:
                self._entries = tuple(
                    sorted(filter(lambda e: e is not None,
                                  map(ChangeLogEntry.from_str, f.readlines())),
                           key=lambda e: e.version))
        return self._entries

    @property
    def today(self) -> Optional[ChangeLogEntry]:
        """only today's changelog entry if there is one for today."""
        date_entries: Tuple[ChangeLogEntry, ...] = tuple(filter(
            lambda e: e.is_today, self.entries))
        if len(date_entries) > 1:
            estr: str = ', '.join(map(str, date_entries))
            raise ProjectRepoError(
                f"Expecting one entry but got {len(date_entries)}: {estr}")
        elif len(date_entries) > 0:
            return date_entries[0]

    def asdict(self) -> Dict[str, Any]:
        entries: List[ChangeLogEntry] = list(map(
            lambda e: e.asdict(), self.entries))
        return {
            'path': str(self.path.absolute()),
            # too much data to make metadata file readable
            #'entries': list(map(lambda e: e.asdict(), self.entries))
            'last_entry': entries[-1] if len(entries) > 0 else None}


@dataclass
class Release(Flattenable):
    """A matching entry between a release tag the change log.

    """
    tag: Tag = field()
    change_log_entry: ChangeLogEntry = field()

    @property
    def date_match(self) -> bool:
        """Whether the dates match between the Git tag and the change log."""
        return self.tag.date == self.change_log_entry.date

    @property
    def version_match(self) -> bool:
        """Whether the versions match between the Git tag and the change log."""
        return self.tag.version == self.change_log_entry.version

    @property
    def issue(self) -> Optional[str]:
        """The human readable reason why release is not valid, or ``None`` if it
        is valid.

        """
        if not self.date_match:
            return 'dates do not match'
        if not self.version_match:
            return 'versions do not match'
        if not self.change_log_entry.is_today:
            return 'the change log is stale'

    def asdict(self) -> Dict[str, Any]:
        issue: str = self.issue
        valid: bool = (issue is None)
        dct = {'valid': valid}
        if valid:
            dct.update(self.tag.asdict())
        return dct
