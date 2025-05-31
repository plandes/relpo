"""Classes that are used to write site documentation.

"""
from __future__ import annotations
__author__ = 'Paul Landes'
from typing import Tuple, List, Dict, Any, Type
from dataclasses import dataclass, field
import os
import sys
from itertools import chain
import logging
import shutil
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Template
from . import ProjectRepoError, Flattenable

logger = logging.getLogger(__name__)


@dataclass
class DocConfig(Flattenable):
    """Configuration for API doc generation.

    """
    data: Dict[str, Any] = field()
    """The parsed document config."""

    stage_dir: Path = field()
    """Where temporary files are created used by Sphinx."""

    config_template_dir: Path = field()
    """The template directory to create the Sphinx API config files."""

    apidoc_template_dir: Path = field()
    """The directory used by ``sphinx-api`` to generate Sphinx RST files.  This
    is the output directory of the :obj:`config_template_dir` config files.

    """
    apidoc_output_dir: Path = field()
    """The ``sphinx-api`` output directory."""

    python_home: Path = field()
    """Sphinx Python environment."""

    api_config: Dict[str, Any] = field()
    """The Sphinx API configuration values."""

    copy: Dict[str, Any] = field()
    """Files to copy to the Sphinx source directory."""

    @staticmethod
    def _get(data: Dict[str, Any], key: str,
             desc: str, default: Any = None) -> Any:
        val = data.get(key, default)
        if val is None:
            raise ProjectRepoError(f"Missing {desc} key '{key}' in <<{data}>>")
        return val

    @classmethod
    def instance(cls: Type, data: Dict[str, Any]) -> DocConfig:
        return DocConfig(
            data=data,
            config_template_dir=Path(cls._get(
                data, 'config_template_dir', 'directory with config templates')),
            apidoc_template_dir=Path(cls._get(
                data, 'apidoc_template_dir', 'directory RST config files')),
            stage_dir=Path(cls._get(
                data, 'stage_dir', 'sphinx temporary files directory')),
            apidoc_output_dir=Path(cls._get(
                data, 'apidoc_output_dir', 'the sphinx-api output director')),
            python_home=Path(cls._get(
                data, 'python_home', 'Sphinx Python environment',
                Path(sys.executable).parent.parent)),
            api_config=cls._get(
                data, 'api_config', 'sphinx API config values'),
            copy=cls._get(
                data, 'copy', 'verbatim file patterns to copy'))

    def asdict(self):
        return self.data


@dataclass
class Documentor(object):
    """This class creates files used by ``sphinx-api`` and ``sphinx-build`` to
    create a package API documentation.  First rendered (from Jinja2 templates)
    Sphinx configuration (i.e. ``.rst`` files) and static files are written to a
    source directory.  Then Sphinx is given the source directory to generate the
    API documentation.

    """
    config: DocConfig = field()
    """The parsed document generation configuration."""

    template_params: Dict[str, Any] = field()
    """The context given to Jinja2 as :class:`.Project` used to render the
    Sphinx API docs.

    """
    temporary_dir: Path = field()
    """Temporary space for files."""

    output_dir: Path = field()
    """Where to output the generated site."""

    def __post_init__(self):
        self._stage_dir = self.temporary_dir / self.config.stage_dir

    def _generate_apidoc_config(self):
        """Render Sphinx config templates and write to the Sphinx source
        directory.

        """
        template_dir: Path = self.config.config_template_dir
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug('generating site with:')
            for line in self.config.asyaml().strip().split('\n'):
                logger.debug(f'  {line}')
        env = Environment(loader=FileSystemLoader(template_dir))
        tfile: Path
        for tfile in template_dir.iterdir():
            out_file: Path = self._stage_dir / tfile.name
            if logger.isEnabledFor(logging.INFO):
                logger.info(f'template: {tfile} -> {out_file}')
            template: Template = env.get_template(tfile.name)
            content: str = template.render(**self.template_params)
            out_file.write_text(content + '\n')

    def _copy_static_source(self):
        """Copy files provided in the doc config to the sphinx source
        directory.

        """
        def map_src_dst(src: str, dst: Any) -> Path:
            if dst is None:
                dst = src
            return (Path(src), self._stage_dir / dst)

        copies: Dict[str, Any] = self.config.copy
        src: str
        dst: str
        for src, dst in map(lambda t: map_src_dst(*t), copies.items()):
            if src.is_file():
                if logger.isEnabledFor(logging.INFO):
                    logger.info(f'copying file: {src} -> {dst}')
                shutil.copyfile(src, dst)
            elif src.is_dir():
                shutil.copytree(src, dst)
            else:
                logger.warning(f'file does not exist: {src}--skipping')

    def _execute(self, cmd: List[str]):
        cmd_line: str = ' '.join(cmd)
        logger.info(f'executing: {cmd_line}')
        os.system(cmd_line)

    def _resolve_bin(self, name: str) -> Path:
        return str(self.config.python_home / 'bin' / name)

    def _generate_rst(self):
        """Look in source (module paths) Python modules and packages and create
        one reST file with automodule directives per package.

        """
        apidoc_out: Path = self.temporary_dir / self.config.apidoc_output_dir
        prog: str = self._resolve_bin('sphinx-apidoc')
        module_top_dirs: List[str] = self.config.api_config['source_dirs']
        module_dirs: Tuple[str, ...] = tuple(map(str, chain.from_iterable(
            map(lambda p: Path(p).iterdir(), module_top_dirs))))
        module_path: str = module_dirs[0]
        for path in module_dirs[1:]:
            if logger.isEnabledFor(logging.INFO):
                logger.info(f'adding additional module dir: {path}')
            sys.path.append(path)
        cmd: List[str] = (
            [prog] +
            '-fT --implicit-namespaces'.split() +
            ['--templatedir', str(self.config.apidoc_template_dir)] +
            ['-o', str(apidoc_out), module_path])
        self._execute(cmd)

    def _generate_html(self):
        prog: str = self._resolve_bin('sphinx-build')
        cmd: List[str] = (
            [prog] +
            '-M html'.split() +
            [str(self._stage_dir), str(self.output_dir)])
        self._execute(cmd)

    def generate(self):
        """Create the site and API documentation."""
        for path in (self._stage_dir, self.output_dir):
            logger.info(f'removing existing doc source tree: {path}')
            if path.is_dir():
                shutil.rmtree(path)
        self._stage_dir.mkdir(parents=True, exist_ok=True)
        self._generate_apidoc_config()
        self._copy_static_source()
        self._generate_rst()
        self._generate_html()
