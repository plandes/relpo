"""Conda metadata utility.

"""
__author__ = 'Paul Landes'

from typing import Tuple, Dict, Any, Iterable
from dataclasses import dataclass, field
from pathlib import Path
import yaml
import zipfile
import zstandard
import tarfile
from . import ProjectRepoError


class CondaPackageError(ProjectRepoError):
    """Raised for Conda package parsing issues."""
    pass


@dataclass
class CondaPackage(object):
    """Parse and retrieve Conda package metadata.

    """
    path: Path = field()
    """The Conda package file path."""

    def _get(self, data: Dict[str, Any], key: str, desc: str) -> Any:
        val: Any = data.get(key)
        if val is None:
            raise CondaPackageError(
                f'Missing {desc} ({key}) in conda package ' +
                f'file {self.path}')
        return val

    def _get_conda_package_info(self) -> Iterable[Tuple[str, Dict[str, bytes]]]:
        """Extract conda package info files from conda pkg file.

        :link: `Stack: <https://stackoverflow.com/questions/61900525/how-do-i-see-the-summary-or-description-for-a-conda-package>`_

        """
        with zipfile.ZipFile(self.path, 'r') as cf:
            cf_name: str
            for cf_name in cf.namelist():
                if cf_name.startswith('info') and cf_name.endswith('.tar.zst'):
                    with cf.open(cf_name) as inf:
                        unzstd = zstandard.ZstdDecompressor()
                        with unzstd.stream_reader(inf) as stream:
                            with tarfile.open(mode='r|', fileobj=stream) as tf:
                                yield cf_name, {
                                    member.name: tf.extractfile(member).read()
                                    for member in tf if not member.isdir()}

    @property
    def metadata(self) -> Dict[str, bytes]:
        """The metadata parsed from the :obj:`path` file."""
        if not hasattr(self, '_metadata'):
            pkgs: Tuple[Tuple[str, Dict[str, bytes]], ...] = \
                tuple(self._get_conda_package_info())
            if len(pkgs) != 1:
                raise CondaPackageError(
                    f'Expecting exactly one info file but got {len(pkgs)} ' +
                    f'in conda package file: {self.path}')
            fname, file_data = pkgs[0]
            self._metadata = file_data
        return self._metadata

    @property
    def build_metadata(self) -> Dict[str, Any]:
        """The build metadata parsed from the metadata recipe file."""
        content: bytes = self._get(
            self.metadata, 'info/recipe/meta.yaml', 'recipe metadata')
        meta: Dict[str, Any] = yaml.load(content, yaml.FullLoader)
        return self._get(meta, 'build', 'build metadata')

    @property
    def build_config(self) -> Dict[str, Any]:
        """The build config parsed from the build config recipe file."""
        content: bytes = self._get(
            self.metadata, 'info/recipe/conda_build_config.yaml',
            'recipe build')
        return yaml.load(content, yaml.FullLoader)

    @property
    def is_noarch(self) -> bool:
        """Whether :obj:`path` points to a noarch file."""
        build: Dict[str, Any] = self.build_metadata
        return build.get('noarch') is not None

    @property
    def target_platform(self) -> str:
        """The intended target platform intended for which the package was
        built.  In at least one example (setuptools) this is ``linux-64`` for a
        ``noarch`` file.

        """
        return self._get(self.build_config, 'target_platform', 'platform meta')
