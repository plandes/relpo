from typing import Dict
from util import TestBase
import yaml
from zensols.relpo.envdist import Dependency


class TestEnvironmentDist(TestBase):
    def test_dep_name_ver_parse(self):
        with open('test-resources/dep-test.yml') as f:
            deps_meta = yaml.load(f, yaml.FullLoader)
        dep_meta: Dict[str, str]
        for dep_meta in deps_meta:
            self.assertEqual(1, len(dep_meta))
            dep_type, src_should = tuple(dep_meta.items())[0]
            src, sname, sver = src_should.split()
            dep = Dependency(dep_type == 'conda', src)
            self.assertEqual(dep.name, sname, f'bad name: {dep}')
            self.assertEqual(dep.version, sver, f'bad version: {dep}')
