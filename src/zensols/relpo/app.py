"""A Python project release with Git integration.

"""
__author__ = 'Paul Landes'

from typing import Tuple
from dataclasses import dataclass, field
import logging
import sys
from pathlib import Path
from . import ProjectRepoError, Version, Tag, ChangeLogEntry
from .project import Project, ProjectFactory

logger = logging.getLogger(__name__)


@dataclass
class Application(object):
    """The application client class to the command line.

    """
    config_files: Path = field()
    """The ``relpo.yml`` configuration file used for substitution."""

    temporary_dir: Path = field()
    """Temporary space for files."""

    def _get_project(self, force_clean: bool = False) -> Project:
        fac = ProjectFactory(self.config_files, self.temporary_dir)
        if force_clean:
            fac.reset()
        return fac.create()

    def _dump(self, content: str, out: Path, data_name: str):
        if out is None:
            print(content, end='')
        else:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(content)
            if logger.isEnabledFor(logging.INFO):
                logger.info(f'wrote {data_name} to: {out}')

    def config(self):
        """Output the synthesized build configuration (useful for debugging)."""
        from pprint import pprint
        project: Project = self._get_project()
        pfiles: str = ', '.join(map(str, project.config_files))
        print(f'config files: {pfiles}')
        pprint(project.read_config())

    def meta(self, out: Path = None, format: str = None):
        """Print or write the project metadata.

        :param out: the output file or dump to standard out if not provided

        """
        format = 'json' if format is None else format
        project: Project = self._get_project()
        content: str
        if format == 'json':
            content = project.asjson(indent=4)
            content = content + '\n'
        elif format == 'yaml':
            content = project.asyaml()
        else:
            raise ValueError(f'No such output format: {format}')
        self._dump(content, out, 'build metadata')

    def pyproject(self, out: Path = None):
        """Write the ``pyproject.toml`` file.

        :param out: the output file or dump to standard out if not provided

        """
        project: Project = self._get_project()
        content: str = project.pyproject + '\n'
        self._dump(content, out, 'build metadata')

    def mktag(self, message: str):
        """Create a tag using the last change log entry's version.

        :param message: the message (comment-like) of the tag

        """
        # TODO: recreate the pyproject.toml file on mk, rm, bump tags
        project: Project = self._get_project()
        tags: Tuple[Tag, ...] = project.repo.tags
        changes: Tuple[ChangeLogEntry, ...] = project.change_log.entries
        if len(tags) > 0 and len(changes) > 0 and \
           tags[-1].version == changes[-1].version:
            raise ProjectRepoError(
                f'Tag already exists for latest change log entry: {tags[-1]}')
        else:
            v: Version = changes[-1].version if len(changes) > 0 else Version()
            project.repo.create_tag(v, message)

    def rmtag(self):
        """Remove the most recent tag."""
        project: Project = self._get_project()
        project.repo.delete_last_tag()

    def bumptag(self):
        """Delete the last tag and create a new one on the latest commit."""
        project: Project = self._get_project()
        project.repo.bump_tag()

    def check(self) -> int:
        """Release sanity check (git and change log versions match)."""
        project: Project = self._get_project(True)
        reason: str = project.issue
        if reason is None:
            logger.info('release is valid')
            return 0
        else:
            logger.error(f'error: {reason}')
            return 1

    def template(self):
        """Render a template given as standard in using keys: ``date``,
        ``project``, ``config``.

        """
        project: Project = self._get_project()
        template: str = sys.stdin.read().strip()
        if len(template) == 0:
            raise ProjectRepoError('No standard input template found')
        print(project.render(template))

    def mkdoc(self, out: Path = None):
        """Create the site documentation.

        :param out: the directory to output the documentation

        """
        project: Project = self._get_project(True)
        project.create_doc(out)
