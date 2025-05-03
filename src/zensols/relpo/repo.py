"""Project and git repository classes.

"""
__author__ = 'Paul Landes'

from typing import Tuple, Dict, List, Iterable, Optional, Any
from dataclasses import dataclass, field
import logging
from pathlib import Path
import itertools as it
from datetime import datetime, date
from git import Repo, TagReference
from git import Commit as GitCommit
from . import ProjectRepoError, Flattenable, Version, Commit, Tag

logger = logging.getLogger(__name__)


@dataclass
class GitRemote(Flattenable):
    """A Git remote created with a command such as::

        ``git remote add <name> <url>``

    """
    name: str = field()
    """The remote name."""

    url: str = field()
    """The URL of the remote."""


@dataclass
class ProjectRepo(Flattenable):
    """A Python source code Git repository.  It's main use is determining the
    last tag in a sorted (by version) used to increment to the next version.
    However, it also creates tags and provides additional information about
    existing tags.

    All tags have an implicit format by sorting in decimal format
    (i.e. ``<major>.<minor>.<version>``).

    """
    repo_dir: Path = field()
    """The root Git repo directory."""

    commit_limit: int = field(default=20)
    """The maximum most recent commits to track and returned from
    :obj:`commits`.

    """
    @property
    def git_repo(self) -> Repo:
        if not hasattr(self, '_repo'):
            repo_dir: str = str(self.repo_dir.resolve())
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f'tag object instance repo dir: {repo_dir}')
            try:
                repo = Repo(repo_dir)
            except Exception as e:
                raise ProjectRepoError(
                    f'Can not resolve repo: {repo_dir}: {e}') from e
            assert not repo.bare
            self._repo = repo
        return self._repo

    @property
    def git_remotes(self) -> Tuple[GitRemote, ...]:
        """The Git remotes for this repository."""
        return tuple(map(lambda r: GitRemote(r.name, next(r.urls)),
                         self.git_repo.remotes))

    @property
    def tags(self) -> Tuple[Tag, ...]:
        """Return the tags in the repo in order of version.  Only those that
        match the version pattern are returned.

        """
        if not hasattr(self, '_entries'):
            entries: List[Tag] = []
            tag: TagReference
            for tag in self.git_repo.tags:
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f'tag: {tag}')
                name: str = str(tag)
                version = Version.from_str(name)
                dte: date = None
                if hasattr(tag.object, 'tagged_date'):
                    date_time_t: int = tag.object.tagged_date
                    dte = datetime.fromtimestamp(date_time_t).date()
                if version is not None:
                    entries.append(Tag(
                        date=dte,
                        version=version,
                        name=name,
                        sha=str(tag.commit),
                        message=tag.object.message))
            self._entries = tuple(sorted(entries, key=lambda t: t.version))
        return self._entries

    @property
    def commits(self) -> Tuple[Commit, ...]:
        if not hasattr(self, '_commits'):
            commits: List[Commit] = []
            gcs: Iterable[GitCommit] = self.git_repo.iter_commits('HEAD')
            gc: GitCommit
            for gc in it.islice(gcs, self.commit_limit):
                commits.append(Commit(
                    date=gc.committed_datetime,
                    author=str(gc.author),
                    sha=str(gc),
                    summary=gc.summary))
            commits.reverse()
            self._commits = tuple(commits)
        return self._commits

    def asdict(self) -> Dict[str, Any]:
        """Return information about the last commit and a build time with the
        current time.

        """
        tags: List[Tag] = list(map(lambda t: t.asdict(), self.tags))
        commits: List[Commit] = list(map(lambda t: t.asdict(), self.commits))
        inf: Dict[str, Any] = {
            'remotes': list(map(lambda t: t.asdict(), self.git_remotes)),
            # too much data to make metadata file readable
            #'tags': list(map(lambda t: t.asdict(), self.tags))
            'last_tag': tags[-1] if len(tags) > 0 else None,
            'last_commit': commits[-1] if len(commits) > 0 else None}
        return inf

    def create_tag(self, version: Version, message: str) -> str:
        """Create a new tag.

        :param tag_name: the text of the tag

        :param message: the message (comment-like) of the tag

        """
        tag_name: str = version.name
        if logger.isEnabledFor(logging.INFO):
            logger.info(f'creating {tag_name} with message <{message}>')
        TagReference.create(self.git_repo, tag_name, message=message)
        return tag_name

    def increment_tag(self, message: str,
                      version_increment_level: str = 'debug') -> Version:
        """Create a new tag incremented from the version of the latest commit.

        :param tag_name: the text of the tag

        :param version_increment_level: which part of the version to increment

        """
        tags: Tag = self.tags
        ver: Version
        if len(tags) == 0:
            ver = Version()
        else:
            ver = tags[-1].version.simple
            ver.increment(version_increment_level)
        self.create_tag(ver)
        return ver

    def delete_last_tag(self) -> str:
        """Delete the most recent commit tag."""
        tag: Tag = self.tags[-1]
        if logger.isEnabledFor(logging.INFO):
            logger.info(f'deleting tag: {tag}')
        TagReference.delete(self.git_repo, tag.name)
        return tag

    def bump_tag(self) -> str:
        """Delete the last tag and create a new one on the latest commit."""
        tag: Tag = self.tags[-1]
        if logger.isEnabledFor(logging.INFO):
            logger.info(f'deleting tag: {tag}')
        TagReference.delete(self.git_repo, tag.name)
        if logger.isEnabledFor(logging.INFO):
            logger.info(f'creating tag: {tag}')
        TagReference.create(self.git_repo, tag.name, message=tag.message)
        return tag
