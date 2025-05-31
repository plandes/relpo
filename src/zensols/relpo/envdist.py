"""Environment distribution file build.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import Tuple, List, Dict, Set, Any, Optional, Type, ClassVar
from dataclasses import dataclass, field
import logging
import re
from collections import OrderedDict
from pathlib import Path
import shutil
import requests
from requests import Response
import yaml
from tqdm import tqdm
from jinja2 import Template, BaseLoader
from jinja2 import Environment as Jinja2Environment
from . import ProjectRepoError, Flattenable, Config

logger = logging.getLogger(__name__)


@dataclass
class EnvironmentDistConfig(Config):
    """Configuration for API doc generation.

    """
    cache_dir: Path = field()
    """The directory to cache conda and PyPi library files."""

    pixi_lock_file: Path = field()
    """The pixi lock file (``pixi.lock``)."""

    environment: str = field()
    """The environment to export (i.e. ``default``, ``testur``)."""

    platforms: Set[str] = field()
    """The platforms to export (i.e. ``linux-64``)."""

    injects: Tuple[Tuple[str, bool], ...] = field()
    """Local files to add to the distribution."""

    @classmethod
    def instance(cls: Type, data: Dict[str, Any]) -> EnvironmentDistConfig:
        return EnvironmentDistConfig(
            data=data,
            cache_dir=Path(cls._get(
                data, 'cache_dir', 'cached directory for library files')),
            pixi_lock_file=Path(cls._get(
                data, 'pixi_lock_file', 'the pixi lock file (pixi.lock)')),
            environment=cls._get(
                data, 'environment', 'environment to export'),
            platforms=set(cls._get(
                data, 'platforms', 'platforms to export', set())),
            injects=set(cls._get(
                data, 'injects', 'local file adds to distribution', ())))


@dataclass
class Dependency(Flattenable):
    """A lock dependency.

    """
    _PYPI_ANY_REGEX: ClassVar[re.Pattern] = re.compile(
        r'.+(?:py3-none-any\.whl|tar\.(?:gz|bz2))$')
    _URL_REGEX: ClassVar[re.Pattern] = re.compile(r'^(direct\+)?(http.+)\/(.+)')
    _NAME_VER_REGEX: ClassVar[re.Pattern] = re.compile(
        r'^(^[A-Za-z0-9]+(?:[_-][a-z0-9]+)*)-(.+)((?:-py3|.tar).+)$')
    _NAME_VER_FIRST_REGEX: ClassVar[re.Pattern] = re.compile(
        r'^(^[A-Za-z0-9]+(?:[_-][a-z0-9]+)*)-(V?[0-9.]+(?:-?(?:stable|beta|alpha|RC[0-9]))?)(.+)$')

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
    def is_platform_independent(self) -> bool:
        """Whether this is platform independent (i.e. ``py3-none-any``)."""
        return (not self.is_conda) and \
            self._PYPI_ANY_REGEX.match(self.source) is not None

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
    def name(self) -> str:
        """The dependency name (i.e. ``numpy`` in ``numpy==1.26.0``)."""
        return self._get_name_version()[0]

    @property
    def version(self) -> str:
        """The dependency version (i.e. ``1.26.0`` in ``numpy==1.26.0``)."""
        return self._get_name_version()[1]

    @property
    def native_file(self) -> Optional[Path]:
        """The local file dependency path if :obj:`is_file` is ``True``.  These
        are usually added to the repository and not to be confused with the
        cached / downloaded file.

        :see: :obj:`local_file`

        """
        if self.is_file:
            return Path(self.source)

    @property
    def dist_name(self) -> str:
        """The file name (sans directory) used in the distribution."""
        if self.is_file:
            return self.native_file.name
        else:
            return self.source_file

    def asdict(self) -> Dict[str, Any]:
        dct: Dict[str, Any] = {
            'name': self.name,
            'version': self.version,
            'url': self.url,
            'is_file': self.is_file,
            'is_direct': self.is_direct,
            'is_platform_independent': self.is_platform_independent,
            'native_file': str(self.native_file)}
        dct.update(super().asdict())
        dct.pop('source')
        dct['local_file'] = str(dct['local_file'])
        return dct

    def __str__(self) -> str:
        s: str
        if self.is_file:
            s = str(self.native_file)
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

    dependencies: List[Dependency] = field()
    """The platform dependnecies"""

    def get_subdir(self, dependency: Dependency) -> str:
        if dependency.is_platform_independent:
            return 'pypi'
        else:
            return self.name

    def __len__(self) -> int:
        return len(self.dependencies)

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

    def __len__(self) -> int:
        return sum(map(len, self.platforms.values()))

    def __str__(self) -> str:
        return self.name

    def __repr__(self):
        plats: str = ', '.join(map(str, self.platforms))
        return f"environment '{self.name}' (platform(s): {plats})"


@dataclass
class EnvironmentDistBuilder(Flattenable):
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
        self._stage_dir = self.temporary_dir / 'envdist'
        self._lock: Dict[str, Any] = None
        self._env: Environment = None
        self._pbar: tqdm = None
        self._jinja2_env = Jinja2Environment(
            loader=BaseLoader,
            keep_trailing_newline=True)

    def _render(self, template_content: str, params: Dict[str, Any]) -> str:
        template: Template = self._jinja2_env.from_string(template_content)
        return template.render(**params)

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
        """Parse and return the Pixi lock file as an in-memory object graph."""
        if self._env is None:
            envs: Dict[str, Any] = self.lock['environments']
            env: Dict[str, Any] = envs.get(self.config.environment)
            pkgs: Dict[str, Any] = env['packages']
            plats_avail: Set[str] = set(pkgs.keys())
            plats_conf: Set[str] = self.config.platforms
            plat_names: Set[str] = plats_conf \
                if len(plats_conf) > 0 else plats_avail
            plats_unavail: Set[str] = (plat_names - plats_avail)
            plats: List[Platform] = []
            if len(plats_unavail) > 0:
                plat_str: str = ', '.join(plats_unavail)
                raise ProjectRepoError(
                    f'Exported platforms requested but unavailable: {plat_str}')
            plat_name: str
            for plat_name in plat_names:
                deps: List[Dependency] = []
                plat: Dict[str, Any]
                for plat in pkgs[plat_name]:
                    assert len(plat) == 1
                    dep_type, url = next(iter(plat.items()))
                    if dep_type != 'conda' and dep_type != 'pypi':
                        raise ProjectRepoError(
                            f'Unknown dependency type: {dep_type}')
                    deps.append(Dependency(dep_type[0] == 'c', url))
                plats.append(Platform(plat_name, deps))
            self._env = Environment(
                name=self.config.environment,
                platforms={p.name: p for p in plats})
        return self._env

    def _fetch_or_download(self, platform: Platform, dep: Dependency):
        """Fetch a dependency if it isn't already downloaded and set
        :obj:`.Dependency.file` to the local file.

        :param platform: the platform to which the dependency belongs

        :param dep: the dependency to download and populate

        """
        if dep.is_file:
            assert dep.native_file is not None
            dep.local_file = dep.native_file
        else:
            url: str = dep.url
            base_dir: Path = self.config.cache_dir / platform.get_subdir(dep)
            if not base_dir.is_dir():
                base_dir.mkdir(parents=True)
                logger.info(f'created directory: {base_dir}')
            local_file: Path = base_dir / dep.source_file
            logger.debug(f'{url} -> {local_file}')
            if not local_file.exists():
                logger.debug(f'downloading from {url}')
                res: Response = requests.get(url)
                if res.status_code == 200:
                    with open(local_file, 'wb') as f:
                        f.write(res.content)
                else:
                    raise ProjectRepoError(f'Dependency download fail: {dep}')
            dep.local_file = local_file

    def _download_dependencies(self):
        """Download dependencies for the enviornment's configured platforms."""
        env: Environment = self._get_environment()
        plat: Platform
        for plat in env.platforms.values():
            logger.info(f'creating {repr(plat)} with {len(plat)} dependencies')
            self._pbar.set_description(f'down {plat}')
            dep: Dependency
            for dep in plat.dependencies:
                self._fetch_or_download(plat, dep)
                self._pbar.update()

    def get_environment_file(self, platform_name: str) -> str:
        """The contents of the a platform's Conda ``environment.yml`` file"""
        def relative_path(dep: Dependency) -> str:
            base_dir = Path(plat.get_subdir(dep))
            return str(base_dir / dep.dist_name)

        env: Environment = self._get_environment()
        root: Dict[str, Any] = OrderedDict()
        plat: Platform = env.platforms[platform_name]
        deps: List[Dict[str, Any]] = []
        pdeps: List[str] = []
        root['name'] = '{{ config.project.name  }}-{{ platform.name }}'
        #deps.append('python == {{ config.project.python.version.current }}')
        root['channels'] = ['nodefaults']
        dep: Dependency
        for dep in filter(lambda d: d.is_conda, plat.dependencies):
            deps.append(relative_path(dep))
        deps.append('pip')
        deps.append({'pip': pdeps})
        for dep in filter(lambda d: not d.is_conda, plat.dependencies):
            pdeps.append(relative_path(dep))
        root['dependencies'] = deps
        return self._asyaml(root)

    def _create_tar(self):
        stage_dir: Path = self._stage_dir
        env: Environment = self._get_environment()
        if stage_dir.is_dir():
            logger.info(f'removing existing temporary files: {stage_dir}')
            shutil.rmtree(stage_dir)
        stage_dir.mkdir(parents=True)
        plat: Platform
        for plat in env.platforms.values():
            env_file: Path = stage_dir / 'environment.yml'
            param: Dict[str, Any] = dict(self.template_params)
            param['platform'] = plat
            env_content: str = self.get_environment_file(plat.name)
            env_content = self._render(env_content, param)
            self._pbar.set_description(f'arch {plat}')
            env_file.write_text(env_content)
            logger.info(f'wrote: {env_file}')
            self._pbar.update()
            for dep in plat.dependencies:
                targ: Path = stage_dir / plat.get_subdir(dep) / dep.dist_name
                targ.parent.mkdir(parents=True, exist_ok=True)
                logger.debug(f'{dep.local_file} -> {targ}')
                shutil.copyfile(dep.local_file, targ)
                self._pbar.update()
        logger.info(f'wrote: {self.output_file}')

    def generate(self):
        """Create the environment distribution file."""
        progress: bool = logger.level >= logging.WARNING
        env: Environment = self._get_environment()
        n_deps: int = len(env)
        n_steps: int = (n_deps * 2) + 1
        logger.info(f'creating {repr(env)} with {n_deps} dependencies')
        self._pbar = tqdm(total=n_steps, ncols=80, disable=(not progress))
        self._download_dependencies()
        self._create_tar()
