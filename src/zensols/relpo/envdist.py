"""Environment distribution file build.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import Tuple, List, Dict, Set, Any, Optional, Type, ClassVar
from dataclasses import dataclass, field
import logging
import re
from pathlib import Path
import shutil
import requests
from requests import Response
from tqdm import tqdm
import yaml
from . import ProjectRepoError, Flattenable, Config

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentDistConfig(Config):
    """Configuration for API doc generation.

    """
    stage_dir: Path = field()
    """Where library distribution files are staged."""

    cache_dir: Path = field()
    """The directory to cache conda and PyPi library files."""

    pixi_lock_file: Path = field()
    """The pixi lock file (``pixi.lock``)."""

    environment: str = field()
    """The environment to export (i.e. ``default``, ``testur``)."""

    platforms: Set[str] = field()
    """The platforms to export (i.e. ``linux-64``)."""

    @classmethod
    def instance(cls: Type, data: Dict[str, Any]) -> EnvironmentDistConfig:
        return EnvironmentDistConfig(
            data=data,
            stage_dir=Path(cls._get(
                data, 'stage_dir', 'library distribution files directory')),
            cache_dir=Path(cls._get(
                data, 'cache_dir', 'cached directory for library files')),
            pixi_lock_file=Path(cls._get(
                data, 'pixi_lock_file', 'the pixi lock file (pixi.lock)')),
            environment=cls._get(
                data, 'environment', 'environment to export'),
            platforms=set(cls._get(
                data, 'platforms', 'platforms to export', set())))


@dataclass
class Dependency(Flattenable):
    """A lock dependency."""

    _URL_REGEX: ClassVar[re.Pattern] = re.compile(r'^(direct\+)?(http.+)\/(.+)')
    _NAME_VER_REGEX: ClassVar[re.Pattern] = re.compile(
        r'^(^[A-Za-z0-9]+(?:[_-][a-z0-9]+)*)-(.+)((?:-py3|.tar).+)$')
    _NAME_VER_FIRST_REGEX: ClassVar[re.Pattern] = re.compile(
        r'^(^[A-Za-z0-9]+(?:[_-][a-z0-9]+)*)-(V?[0-9.]+(?:-?(?:stable|beta|alph|RC[0-9]))?)(.+)$')

    is_conda: bool = field()
    """Whether the dependency is ``conda``  as apposed to ``pypi``."""

    source: str = field()
    """The URL of the resource."""

    local_file: Path = field(default=None)
    """The downloaded and cached file on the local file system.

    :see: :obj:`file`

    """
    def _get_url_parts(self) -> Tuple[str, str, str]:
        if not hasattr(self, '_url_parts'):
            m: re.Match = self._URL_REGEX.match(self.source)
            self._url_parts: Tuple[str, ...] = (None, None, None)
            if m is not None:
                self._url_parts = m.groups()
        return self._url_parts

    @property
    def is_file(self) -> bool:
        """Whether or not the dependency is a project local file.  This is not
        to be confused with a cached file downloaded to the local file system.

        """
        return self._get_url_parts()[1] is None

    @property
    def source_file(self) -> str:
        """The file name porition of the url, which is the file name."""
        return self._get_url_parts()[2]

    @property
    def is_direct(self) -> bool:
        """Whether this is a Pip direct URL (i.e. ``<name> @ <url>``)."""
        return self._get_url_parts()[0]

    @property
    def url(self) -> Optional[str]:
        """The URL portion of the source (if it is a URL)."""
        url: Tuple[str, str, str] = self._get_url_parts()
        if url[1] is not None:
            return f'{url[1]}/{url[2]}'

    def _get_name_version(self) -> Tuple[str, str]:
        if not hasattr(self, '_name_version'):
            self._name_version: Tuple[str, ...] = (None, None)
            fname: str = self.source_file
            if fname is not None:
                m: re.Match = self._NAME_VER_REGEX.match(fname)
                if m is None:
                    m = self._NAME_VER_FIRST_REGEX.match(fname)
                if m is not None:
                    self._name_version = m.groups()
        return self._name_version

    @property
    def file(self) -> Optional[Path]:
        """The local file dependency path if :obj:`is_file` is ``True``.  These
        are usually added to the repository and not to be confused with the
        cached / downloaded file.

        :see: :obj:`local_file`

        """
        if self.is_file:
            return Path(self.source)

    @property
    def name(self) -> str:
        return self._get_name_version()[0]

    @property
    def version(self) -> str:
        return self._get_name_version()[1]

    def asdict(self) -> Dict[str, Any]:
        dct: Dict[str, Any] = {
            'is_file': self.is_file,
            'is_direct': self.is_direct,
            'url': self.url,
            'file': str(self.file),
            'name': self.name,
            'version': self.version}
        dct.update(super().asdict())
        dct.pop('source')
        dct['local_file'] = str(dct['local_file'])
        return dct

    def __str__(self) -> str:
        s: str
        if self.is_file:
            s = str(self.file)
        elif self.is_direct:
            s = f'{self.name} @ {self.url}'
        else:
            s = self.source
        return s


@dataclass(repr=False)
class Platform(Flattenable):
    """A parsed platform from the Pixi lock file."""

    name: str = field()
    """The name of the platform (i.e. ``linux-64'``)."""

    deps: List[Dependency] = field()
    """The platform dependnecies"""

    def add_env(self, env: Dict[str, Any]):
        deps: List[Dict[str, Any]] = []
        pdeps: List[str] = []
        dep: Dependency
        for dep in filter(lambda d: d.is_conda, self.deps):
            deps.append(str(dep))
        deps.append('pip')
        deps.append({'pip': pdeps})
        for dep in filter(lambda d: not d.is_conda, self.deps):
            pdeps.append(str(dep))
        env['dependencies'] = deps

    def __len__(self) -> int:
        return len(self.deps)

    def __str__(self) -> str:
        return self.name

    def __repr__(self):
        return f'{self.name} ({len(self)} deps)'


@dataclass(repr=False)
class Environment(Flattenable):
    """A pixi environment."""

    name: str = field()
    """The name of the Pixi enviornment (i.e. ``default``)."""

    platforms: Dict[str, Platform] = field()
    """The Pixi platforms (i.e. ``linux-64``)."""

    def add_env(self, env: Dict[str, Any], platform: str):
        plat: Platform = self.platforms[platform]
        env['name'] = self.name
        plat.add_env(env)

    def env_str(self, platform: str) -> str:
        from collections import OrderedDict
        env: Dict[str, Any] = OrderedDict()
        self.add_env(env, platform)
        return self._asyaml(env)

    def __len__(self) -> int:
        return sum(map(len, self.platforms.values()))

    def __str__(self) -> str:
        return self.name

    def __repr__(self):
        plats: str = ', '.join(map(str, self.platforms))
        return f"environment '{self.name}' (platform(s): {plats})"


@dataclass
class EnvironmentDistBuilder(object):
    """This class creates files used by ``sphinx-api`` and ``sphinx-build`` to
    create a package API documentation.  First rendered (from Jinja2 templates)
    Sphinx configuration (i.e. ``.rst`` files) and static files are written to a
    source directory.  Then Sphinx is given the source directory to generate the
    API documentation.

    """
    _PIXI_LOCK_VERSION: ClassVar[int] = 6

    config: EnvironmentDistConfig = field()
    """The parsed document generation configuration."""

    template_params: Dict[str, Any] = field()
    """The context given to Jinja2 as :class:`.Project` used to render any
    configuration files or install scripts.

    """
    temporary_dir: Path = field()
    """Temporary space for files."""

    output_file: Path = field()
    """Where to output the environment distribution file."""

    def __post_init__(self):
        self._stage_dir = self.temporary_dir / self.config.stage_dir
        self._lock: Dict[str, Any] = None
        self._env: Environment = None
        self._pbar: tqdm = None

    def _assert_valid(self, lock: Dict[str, Any]):
        """Sanity check of the data parsed from the ``pixi.lock`` file."""
        ver: int = lock['version']
        if ver != self._PIXI_LOCK_VERSION:
            raise ProjectRepoError(
                f'Version {self._PIXI_LOCK_VERSION} supprted, got: {ver}')
        if self.config.environment not in lock['environments']:
            raise ProjectRepoError(
                f'Environment {self.config.environment} is not provided')

    @property
    def lock(self) -> Dict[str, Any]:
        """The parsed data from the ``pixi.lock`` file."""
        if self._lock is None:
            with open(self.config.pixi_lock_file) as f:
                self._lock = yaml.load(f, yaml.FullLoader)
            self._assert_valid(self._lock)
        return self._lock

    def _get_environment(self) -> Environment:
        if self._env is None:
            envs: Dict[str, Any] = self.lock['environments']
            env: Dict[str, Any] = envs.get(self.config.environment)
            pkgs: Dict[str, Any] = env['packages']
            plats_avail: Set[str] = set(pkgs.keys())
            plats_conf: Set[str] = self.config.platforms
            plat_ids: Set[str] = plats_conf \
                if len(plats_conf) > 0 else plats_avail
            plats_unavail: Set[str] = (plat_ids - plats_avail)
            plats: List[Platform] = []
            if len(plats_unavail) > 0:
                plat_str: str = ', '.join(plats_unavail)
                raise ProjectRepoError(
                    f'Exported platforms requested but unavailable: {plat_str}')
            plat_id: str
            for plat_id in plat_ids:
                deps: List[Dependency] = []
                plat: Dict[str, Any]
                for plat in pkgs[plat_id]:
                    assert len(plat) == 1
                    dep_type, url = next(iter(plat.items()))
                    if dep_type != 'conda' and dep_type != 'pypi':
                        raise ProjectRepoError(
                            f'Unknown dependency type: {dep_type}')
                    deps.append(Dependency(dep_type[0] == 'c', url))
                plats.append(Platform(plat_id, deps))
            self._env = Environment(
                name=self.config.environment,
                platforms={p.name: p for p in plats})
        return self._env

    def _fetch_or_download(self, dep: Dependency, base_dir: Path):
        if dep.is_file:
            assert dep.file is not None
            dep.local_file = dep.file
        else:
            url: str = dep.url
            local_file: Path = base_dir / dep.source_file
            if not local_file.exists():
                logger.debug(f'{url} -> {local_file}')
                res: Response = requests.get(url)
                if res.status_code == 200:
                    with open(local_file, 'wb') as f:
                        f.write(res.content)
                else:
                    raise ProjectRepoError(f'Dependency download fail: {dep}')
            dep.local_file = local_file

    def _download_dependencies(self):
        cache_dir: Path = self.config.cache_dir
        env: Environment = self._get_environment()
        if not cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f'created directory: {cache_dir}')
        plat: Platform
        for plat in env.platforms.values():
            plat_cache: Path = cache_dir / plat.name
            plat_cache.mkdir(parents=True, exist_ok=True)
            logger.info(f'creating {repr(plat)} with {len(plat)} dependencies')
            logger.debug(f'patform cache dir: {plat_cache}')
            self._pbar.set_description(f'dl {plat}')
            dep: Dependency
            for dep in plat.deps:
                self._fetch_or_download(dep, plat_cache)
                self._pbar.update()

    def get_environment_file(self, platform_id: str) -> str:
        env: Environment = self._get_environment()
        return env.env_str(platform_id)

    def _create_tar(self):
        stage_dir: Path = self._stage_dir
        if stage_dir.is_dir():
            logger.info(f'removing existing temporary files: {stage_dir}')
            shutil.rmtree(stage_dir)
        logger.info(f'wrote: {self.output_file}')

    def generate(self, progress: bool = 0):
        """Create the environment distribution file."""
        env: Environment = self._get_environment()
        n_deps: int = len(env)
        n_steps: int = n_deps * 4
        self._pbar = tqdm(total=n_steps, ncols=80, disable=(not progress))
        #logger.info(f'creating {repr(env)} with {n_deps} dependencies')
        self._download_dependencies()
