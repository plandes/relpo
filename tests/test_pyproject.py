import subprocess as sub
from pathlib import Path
from datetime import datetime
from jinja2 import Template, Environment, FileSystemLoader
from zensols.relpo.project import Project
from util import TestMultiline


class TestPyProject(TestMultiline):
    def _render(self, path: Path):
        env = Environment(loader=FileSystemLoader(path.parent))
        template: Template = env.get_template(path.name)
        cmd: str = "git tag --sort='-version:refname' | head -1"
        version = sub.check_output(cmd, shell=True, text=True)
        version = version.strip()[1:]
        return template.render(
            date=datetime.now(),
            version=version)

    def test_render(self):
        project = Project((Path('test-resources/relpo.yml'),), Path('targt'))
        should: str = self._render(Path('test-resources/pyproject-gold.toml'))
        content: str = project.pyproject
        self.assertEqual(should, content)
