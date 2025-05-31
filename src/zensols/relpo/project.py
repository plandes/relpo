"""A utility class that represents a Git tag.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import Tuple, Dict, Set, List, Any, Type, ClassVar
from dataclasses import dataclass, field
import os
import logging
from datetime import datetime
import functools
from pathlib import Path
import pickle
from io import TextIOBase, StringIO
import yaml
from jinja2 import Template, Environment, FileSystemLoader, BaseLoader
import tomlkit as toml
from tomlkit.toml_document import TOMLDocument
from tomlkit.items import Table
from . import (
    ProjectRepoError, Flattenable,
    Version, Commit, Tag, ChangeLogEntry, Release, ChangeLog
)
from .repo import ProjectRepo
from .doc import DocConfig, Documentor

logger = logging.getLogger(__name__)


@dataclass
class ProjectConfig(Flattenable):
    """The :class:`.Project` configuration.

    """
    data: Dict[str, Any] = field()
    """The raw nested dict data as parsed from the config file."""

    proj_dir: Path = field()
    """The root Git repo directory."""

    template_dir: Path = field()
    """The directory with the ``pyproject.toml`` Jinja2 template files."""

    pyproject_template_files: Tuple[Path, ...] = field()
    """Additional template files used to render the ``pyproject.toml`` file."""

    table_appends: Dict[str, Any] = field()
    """Table name/value TOML appends to add to the ``pyproject.toml`` file.
    These entries have the TOML path as keys and the contents of an inline table
    to add as values.

    """
    change_log_file_name: str = field()
    """The name of the change log file."""

    @staticmethod
    def _get(data: Dict[str, Any], key: str,
             desc: str, default: Any = None) -> Any:
        val = data.get(key, default)
        if val is None:
            raise ProjectRepoError(f"Missing {desc} key '{key}' in <<{data}>>")
        return val

    @classmethod
    def instance(cls: Type, data: Dict[str, Any]) -> ProjectConfig:
        """Create an instance from parsed ``data``."""
        if 'build' not in data:
            raise ProjectRepoError("Missing top-level 'build' from config")
        build: Dict[str, Any] = data['build']
        template_dir: Path = Path(cls._get(
            build, 'template_dir', 'template directory'))
        if not template_dir.is_dir():
            raise ProjectRepoError(
                f'No such template directory: {template_dir}')
        config = ProjectConfig(
            data=data,
            proj_dir=Path(cls._get(
                build, 'project_dir', 'project directory', '.')),
            template_dir=template_dir,
            change_log_file_name=cls._get(
                build, 'change_log_file_name', 'CHANGELOG.md'),
            pyproject_template_files=tuple(cls._get(
                build, 'pyproject_template_files',
                'pyproject.toml project template files', [])),
            table_appends=cls._get(
                build, 'table_appends', 'table name/value TOML appends', {}))
        return config

    @property
    def site_doc_config(self) -> DocConfig:
        config: Dict[str, Any] = self._get(
            self.data, 'doc', 'documentation configuration')
        return DocConfig.instance(config)

    def asdict(self):
        return self.data


@dataclass
class Project(Flattenable):
    """The project and related data of a Python source code repository.

    """
    _PYPROJECT_FILE: ClassVar[str] = 'pyproject.toml'

    config_files: Tuple[Path, ...] = field()
    """The project config files used to populate templates and docs."""

    temporary_dir: Path = field()
    """Temporary space for files."""

    def read_config(self) -> List[Dict[str, Any]]:
        """Return the parsed :obj:`config_files` with each configuration file as
        an element of the returned list.

        """
        template_params: Dict[str, Any] = dict(
            project=self,
            date=datetime.now(),
            env=os.environ)
        datas: List[Dict[str, Any]] = []
        for path in self.config_files:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f'parsing config file: {path}')
            with open(path, 'r') as f:
                content: str = f.read()
            content = self.render(content, template_params)
            datas.append(yaml.load(StringIO(content), yaml.FullLoader))
        return datas

    @property
    def config(self) -> ProjectConfig:
        """The project config used to populate templates.  This is the parsed
        data from all configuration files (:obj:`config_files`).

        """
        def merge(a: dict, b: dict, path=[]) -> dict:
            """Recursively merge dicts.

            :see: `Stackoverflow <https://stackoverflow.com/questions/7204805/deep-merge-dictionaries-of-dictionaries-in-python>`_
            """
            for key in b:
                if key in a:
                    if isinstance(a[key], dict) and isinstance(b[key], dict):
                        merge(a[key], b[key], path + [str(key)])
                    # allow overriding data giving preference to earlier dicts
                    # elif a[key] != b[key]:
                    #     raise Exception('Conflict at ' + '.'.join(path + [str(key)]))
                else:
                    a[key] = b[key]
            return a

        if not hasattr(self, '_config'):
            datas: List[Dict[str, Any]] = self.read_config()
            data: Dict[str, Any] = functools.reduce(merge, datas)
            self._config = ProjectConfig.instance(data)
        return self._config

    def _check_proj_dir(self, raise_error: bool = False) -> str:
        reason: str = None
        proj_dir: Path = self.config.proj_dir.absolute()
        git_dir: Path = self.config.proj_dir / '.git'
        if not self.config.proj_dir.is_dir():
            reason = f'project directory missing or not a directory: {proj_dir}'
        if not git_dir.is_dir():
            reason = f'git directory missing: {proj_dir}'
        if raise_error and reason is not None:
            raise ProjectRepoError(reason.capitalize())
        return reason

    @property
    def repo(self) -> ProjectRepo:
        """The Git repository and its metadata."""
        self._check_proj_dir(True)
        if not hasattr(self, '_repo'):
            self._repo = ProjectRepo(self.config.proj_dir)
        return self._repo

    @property
    def change_log(self) -> ChangeLog:
        """The change log found in the release."""
        if not hasattr(self, '_change_log'):
            clf: Path = self.config.proj_dir / self.config.change_log_file_name
            if not clf.is_file():
                raise ProjectRepoError(f'Change log not found: {clf}')
            self._change_log = ChangeLog(clf)
        return self._change_log

    @property
    def releases(self) -> Tuple[Release, ...]:
        changes: Tuple[ChangeLogEntry, ...] = self.change_log.entries
        tags: Tuple[Tag, ...] = self.repo.tags
        vtoc: Dict[Version, ChangeLogEntry] = {c.version: c for c in changes}
        vtot: Dict[Version, Tag] = {t.version: t for t in tags}
        match_vers: Set[Version] = set(vtoc.keys()) & set(vtot.keys())
        return tuple(map(lambda v: Release(vtot[v], vtoc[v]),
                         sorted(match_vers)))

    def asdict(self) -> Dict[str, Any]:
        rels: Tuple[Release, ...] = self.releases
        return {
            'date': datetime.now().isoformat(),
            'path': str(self.config.proj_dir.absolute()),
            'repo': self.repo.asdict(),
            'change_log': self.change_log.asdict(),
            'last_release': None if len(rels) == 0 else rels[-1].asdict(),
            'issue': self.issue,
            'config': self.config.asdict()}

    def _get_template_params(self) -> Dict[str, Any]:
        """The context given to Jinja2 as :class:`.Project` used to render the
        pyproject.toml file.

        """
        if not hasattr(self, '_template_params'):
            self._template_params = dict(
                project=self,
                date=datetime.now(),
                env=os.environ,
                config=self.config.data)
        return self._template_params

    def _render(self, env: Environment, params: Dict[str, Any],
                template_dir: Path, name: str, writer: TextIOBase):
        template_file: Path = template_dir / name
        if not template_file.is_file():
            raise ProjectRepoError(f'Template file not found: {template_file}')
        template: Template = env.get_template(name)
        writer.write(template.render(**params))
        writer.write('\n')

    def render(self, template_content: str,
               params: Dict[str, Any] = None) -> str:
        """Render a template using:

            * ``date``: the current (now) :class:`~datetime.datetime`
            * ``project``: a reference to *this* class instance
            * ``env``: operating system environment
            * ``config``: the project config (:obj:`config`)

        """
        env = Environment(loader=BaseLoader, keep_trailing_newline=True)
        template: Template = env.from_string(template_content)
        params = self._get_template_params() if params is None else params
        return template.render(params)

    def _append_tables(self, content: str, appends: Dict[str, Any]) -> str:
        proj: TOMLDocument = toml.parse(content)
        pl: List[str]
        src: Dict[str, Any]
        for pl, src in map(lambda i: (i[0].split('.'), i[1]), appends.items()):
            path: List[str] = pl[:-1]
            to_add_name: str = pl[-1]
            to_add = toml.inline_table()
            child: Table = proj
            name: str
            for name in path:
                child = child[name]
            for k, v in src.items():
                to_add.add(k, v)
            child.append(to_add_name, to_add)
        content = toml.dumps(proj)
        return content

    @property
    def pyproject(self) -> str:
        """The ``pyproject.toml`` rendered content as a string.

        :param template_dir: the directory to the zenbuild toml template files

        """
        template_dir: Path = self.config.template_dir
        lib_env = Environment(loader=FileSystemLoader(template_dir))
        local_env = Environment(loader=FileSystemLoader(self.config.proj_dir))
        sio = StringIO()
        params: Dict[str, Any] = self._get_template_params()
        self._render(lib_env, params, template_dir, self._PYPROJECT_FILE, sio)
        name: str
        for name in self.config.pyproject_template_files:
            self._render(local_env, params, self.config.proj_dir, name, sio)
        content: str = sio.getvalue()
        if len(self.config.table_appends) > 0:
            content = self._append_tables(content, self.config.table_appends)
        content = content.rstrip()
        return content

    @property
    def issue(self) -> str:
        """The human readable reason why release is not valid, or ``None`` if it
        is valid.

        """
        reason: str = self._check_proj_dir(False)
        if reason is None:
            changes: Tuple[ChangeLogEntry, ...] = self.change_log.entries
            tags: Tuple[Tag, ...] = self.repo.tags
            commits: Tuple[Commit, ...] = self.repo.commits
            if len(commits) == 0:
                reason = 'nothing to release'
            elif len(changes) == 0:
                reason = 'no change log entries'
            elif len(tags) == 0:
                reason = 'no tag entries'
            elif tags[-1].sha != commits[-1].sha:
                reason = 'there is no tag for the latest commit'
            elif tags[-1].version < changes[-1].version:
                reason = 'there is no tag for latest change log'
            if reason is None:
                rels: Tuple[Release, ...] = self.releases
                if len(rels) == 0:
                    reason = 'no matching releases'
                else:
                    rel: Release = self.releases[-1]
                    reason = rel.issue
        return reason

    def create_doc(self, output_dir: Path):
        """Create the site and API documentation."""
        sd = Documentor(
            config=self.config.site_doc_config,
            template_params=self._get_template_params(),
            temporary_dir=self.temporary_dir,
            output_dir=output_dir)
        sd.generate()


@dataclass
class ProjectFactory(object):
    """Creates and caches the project data.

    """
    config_files: Tuple[Path, ...] = field()
    """The project config files used to populate templates and docs."""

    temporary_dir: Path = field()
    """Temporary space for files."""

    def __post_init__(self):
        self._cache_file: Path = self.temporary_dir / 'build.pkl'

    def _save(self, rel: Project):
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'caching project: {self._cache_file}')
        with open(self._cache_file, 'wb') as f:
            pickle.dump(rel, f)

    def _load(self) -> Project:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f'using cached project: {self._cache_file}')
        with open(self._cache_file, 'rb') as f:
            return pickle.load(f)

    def _latest_config_mtime(self) -> int:
        return max(map(lambda p: p.stat().st_mtime, self.config_files))

    def create(self) -> Project:
        project: Project = None
        if self._cache_file.is_file():
            project = self._load()
            pc_mtime: int = self._cache_file.stat().st_mtime
            is_stale: bool = self._latest_config_mtime() > pc_mtime or \
                project.proj_dir.stat().st_mtime > pc_mtime
            if is_stale:
                project = None
        if project is None:
            project = Project(self.config_files, self.temporary_dir)
        return project

    def reset(self):
        if self._cache_file.is_file():
            self._cache_file.unlink()
