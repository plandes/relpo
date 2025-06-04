"""Environment distribution file build.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import Tuple, List, Dict, Set, Any, Optional, Type, ClassVar
from dataclasses import dataclass, field
import logging
import os
import re
from collections import OrderedDict
from pathlib import Path
import shutil
import requests
from requests import Response
import tarfile
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

    injects: Dict[str, List[Dict[str, str]]] = field()
    """Local files as glob patterns to add to the distribution."""

    @staticmethod
    def _glob_to_paths(injects: Dict[str, List[Dict[str, str]]]):
        """Replace glob patterns with file expanded patterns."""
        # iterate over platforms
        plat: str
        pats: List[Dict[str, str]]
        for plat, pats in injects.items():
            repls: List[Dict[str, str]] = []
            # iterate over the platform's file patterns (each follows the Conda
            # environment forms as a dict with one 'conda' / 'pypi' -> URL/file)
            pat: Dict[str, str]
            for pat in pats:
                assert len(pat) == 1
                dep_type: str
                src: str
                dep_type, src = tuple(pat.items())[0]
                if src.find('*') == -1:
                    # keep exactly what we had
                    repls.append(pat)
                else:
                    # found a glob pattern so assume it is a file
                    repls.extend(map(
                        lambda p: {dep_type: str(p)}, Path('.').glob(src)))
            pats[:] = repls

    @classmethod
    def instance(cls: Type, data: Dict[str, Any]) -> EnvironmentDistConfig:
        injects: Dict[str, List[Dict[str, str]]] = cls._get(
            data, 'injects', 'local file adds to distribution', {})
        cls._glob_to_paths(injects)
        return EnvironmentDistConfig(
            data=data,
            cache_dir=cls._get_path(
                data, 'cache_dir', 'cached directory for library files'),
            pixi_lock_file=cls._get_path(
                data, 'pixi_lock_file', 'the pixi lock file (pixi.lock)'),
            environment=cls._get(
                data, 'environment', 'environment to export'),
            platforms=set(cls._get(
                data, 'platforms', 'platforms to export', set())),
            injects=injects)


@dataclass
class Dependency(Flattenable):
    """A lock dependency.

    """
    _PYPI_ANY_REGEX: ClassVar[re.Pattern] = re.compile(
        r'.+(?:py3-none-any\.whl|tar\.(?:gz|bz2))$')
    _URL_REGEX: ClassVar[re.Pattern] = re.compile(r'^(direct\+)?(http.+)\/(.+)')
    _NAME_VER_REGEXS: ClassVar[re.Pattern] = (
        re.compile(r'^([A-Za-z0-9-_.]+)-([^-]*)-(.*\.(?:conda|tar\.bz2))$'),
        re.compile(r'^(.+)-(.+?)-(?:py2\.)?py3-none-any.whl$'),
        re.compile(r'^([A-Za-z0-9.]+(?:[_-][a-z0-9]+)*)-(.+)((?:-py3|.tar).+)$'),
        re.compile(r'^([A-Za-z0-9.]+(?:[_-][a-z0-9]+)*)-(V?[0-9.]+(?:-?(?:stable|beta|alpha|RC[0-9]))?)(.+)$'))
    _CONDA_ARCH_REGEX: ClassVar[re.Pattern] = re.compile(
        r'^http.*\/conda-forge\/([^\/]+)\/(.+).+$')

    is_conda: bool = field()
    """Whether the dependency is ``conda``  as apposed to ``pypi``."""

    source: str = field()
    """The URL of the resource."""

    def __post_init__(self):
        self._local_file = None

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
    def conda_platform(self) -> Optional[str]:
        """The platform of the conda dependency, or ``None`` if not a conda
        dependnecy.

        """
        if self.is_conda:
            pat: re.Pattern = self._CONDA_ARCH_REGEX
            m: re.Match = pat.match(self.source)
            return m.group(1)

    @property
    def is_platform_independent(self) -> bool:
        """Whether this is platform independent (i.e. ``py3-none-any``)."""
        if self.is_conda:
            return self.conda_platform == 'noarch'
        else:
            return self._PYPI_ANY_REGEX.match(self.source) is not None

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
                pat: re.Pattern
                for pat in self._NAME_VER_REGEXS:
                    m: re.Match = pat.match(fname)
                    if m is not None:
                        self._name_version = m.groups()
                        break
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

    @property
    def local_file(self) -> Path:
        """The downloaded and cached file on the local file system.

        :see: :obj:`file`

        """
        return self._local_file

    @local_file.setter
    def local_file(self, local_file: Path):
        self._local_file = local_file
        if hasattr(self, '_conda_package'):
            del self._conda_package

    def asdict(self) -> Dict[str, Any]:
        dct: Dict[str, Any] = {
            'name': self.name,
            'version': self.version,
            'url': self.url,
            'is_file': self.is_file,
            'is_direct': self.is_direct,
            'native_file': str(self.native_file)}
        dct.update(super().asdict())
        dct.pop('source')
        dct['local_file'] = str(self.local_file)
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
    """Version of the ``pixi.lock`` file currently supported in this library."""

    _PYPI_NAME: ClassVar[str] = 'pypi'
    """The sub directory name for pypi packages added to the distribution."""

    _LOCAL_CHANNEL: ClassVar[str] = 'local-channel'
    """The sub directory used for the conda channel local file directory."""

    _ENV_FILE: ClassVar[str] = 'environment.yml'
    """The ``conda env create`` environment file suffix."""

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

    progress: bool = field()
    """Whether to display the progress bar."""

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
            all_injects = self.config.injects.get('all', {})
            plat_name: str
            for plat_name in plat_names:
                deps: List[Dependency] = []
                dep_specs: List[Dict[str, Any]] = list(pkgs[plat_name])
                plat_injects = self.config.injects.get(plat_name, {})
                dep_specs.extend(all_injects)
                dep_specs.extend(plat_injects)
                dep: Dict[str, Any]
                for dep in dep_specs:
                    assert len(dep) == 1
                    dep_type: str
                    src: str
                    dep_type, src = next(iter(dep.items()))
                    if dep_type != 'conda' and dep_type != 'pypi':
                        raise ProjectRepoError(
                            f'Unknown dependency type: {dep_type}')
                    deps.append(Dependency(dep_type[0] == 'c', src))
                plats.append(Platform(plat_name, deps))
            self._env = Environment(
                name=self.config.environment,
                platforms={p.name: p for p in plats})
        return self._env

    def _get_subdir(self, dep: Dependency, plat: Platform,
                    conda_dir_name: str = 'conda',
                    flatten_pypi: bool = False) -> str:
        par_dir: str
        sub_dir: str = None
        is_ind: bool = dep.is_platform_independent
        if dep.is_conda:
            par_dir = conda_dir_name
            if is_ind:
                sub_dir = 'noarch'
            else:
                sub_dir = plat.name
        else:
            par_dir = self._PYPI_NAME
            if not flatten_pypi:
                if is_ind:
                    sub_dir = 'noarch'
                else:
                    sub_dir = plat.name
        if sub_dir is None:
            return par_dir
        else:
            return str(Path(par_dir, sub_dir))

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
            subdir: str = self._get_subdir(dep, platform)
            base_dir: Path = self.config.cache_dir / subdir
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
            if dep.is_file:
                subdir: str = self._get_subdir(dep, plat, flatten_pypi=True)
                return str(Path(subdir) / dep.native_file.name)
            if dep.name is None:
                raise ProjectRepoError(f'Dependency has no name: {dep}')
            return f'{dep.name}=={dep.version}'

        env: Environment = self._get_environment()
        root: Dict[str, Any] = OrderedDict()
        plat: Platform = env.platforms[platform_name]
        deps: List[Dict[str, Any]] = []
        pdeps: List[str] = []
        root['name'] = self._render(
            template_content='{{ config.project.name  }}',
            params=self.template_params)
        root['channels'] = ['./local-channel', 'nodefaults']
        dep: Dependency
        for dep in filter(lambda d: d.is_conda, plat.dependencies):
            deps.append(relative_path(dep))
        deps.append({'pip': pdeps})
        pdeps.extend(['--no-index', f'--find-links ./{self._PYPI_NAME}'])
        for dep in filter(lambda d: not d.is_conda, plat.dependencies):
            pdeps.append(relative_path(dep))
        root['dependencies'] = deps
        return self._asyaml(root)

    def _stage_tar(self):
        stage_dir: Path = self._stage_dir
        env: Environment = self._get_environment()
        if stage_dir.is_dir():
            logger.info(f'removing existing temporary files: {stage_dir}')
            shutil.rmtree(stage_dir)
        stage_dir.mkdir(parents=True)
        plat: Platform
        for plat in env.platforms.values():
            env_file: Path = stage_dir / f'{plat.name}-{self._ENV_FILE}'
            param: Dict[str, Any] = dict(self.template_params)
            param['platform'] = plat
            env_content: str = self.get_environment_file(plat.name)
            env_content = self._render(env_content, param)
            self._pbar.set_description(f'copy {plat}')
            env_file.write_text(env_content)
            logger.info(f'wrote: {env_file}')
            self._pbar.update()
            for dep in plat.dependencies:
                sub_dir: str = self._get_subdir(
                    dep, plat, self._LOCAL_CHANNEL, True)
                targ: Path = stage_dir / sub_dir / dep.dist_name
                if targ.is_file():
                    continue
                targ.parent.mkdir(parents=True, exist_ok=True)
                logger.debug(f'{dep.local_file} -> {targ}')
                shutil.copyfile(dep.local_file, targ)
                self._pbar.update()
            channel_dir: str = f'{stage_dir}/{self._LOCAL_CHANNEL}'
            cmd: str = f'( cd {channel_dir}  ; conda index . )'
            if logger.level < logging.WARNING:
                cmd += ' > /dev/null 2>&1'
            os.system(cmd)
        return stage_dir

    def _create_tar(self):
        stage_dir: Path = self._stage_dir
        logger.debug(f'staging: {stage_dir}')
        self._pbar.set_description('archive')
        with tarfile.open(self.output_file, 'w') as tar:
            tar.add(stage_dir, arcname=self.output_file.stem)
        self._pbar.update()
        logger.info(f'wrote: {self.output_file}')

    def generate(self):
        """Create the environment distribution file."""
        env: Environment = self._get_environment()
        n_deps: int = len(env)
        n_steps: int = (n_deps * 2) + 2
        logger.info(f'creating {repr(env)} with {n_deps} dependencies')
        self._pbar = tqdm(total=n_steps, ncols=80, disable=(not self.progress))
        self._download_dependencies()
        self._stage_tar()
        self._create_tar()
