"""A utility class that represents a Git remote.

"""
__author__ = 'Paul Landes'

from typing import Tuple, Iterable
import logging
from pathlib import Path
from git import Repo

logger = logging.getLogger(__name__)


class RemoteSet(object):
    """Represents a Git remote.  This is used to populate build metadata used
    for other aspects of the build process rather than just ``setuptools``.

    """
    def __init__(self, repo_dir: Path = Path('.')):
        """Initialize.

        :param repo_dir: the root Git repo directory
        """
        logger.debug('creating remote witih repo dir: {}'.format(repo_dir))
        self.repo = Repo(repo_dir)

    def __iter__(self) -> Iterable[Tuple[str, str]]:
        return map(lambda r: (r.name, next(r.urls)), self.repo.remotes)
