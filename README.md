# Release and Git Repository Automation

[![PyPI][pypi-badge]][pypi-link]
[![Python 3.14][python314-badge]][python314-link]
[![Python 3.13][python313-badge]][python313-link]
[![Build Status][build-badge]][build-link]

A Python project release with Git integration.  This program uses a
configuration file (`relpo.yaml`) to create a `pyproject.toml` file to maintain
projects with [pixi].

Features:

* Track versions using Git tags rather than having to keep versions in files in
  sync with the repository
* Create Sphinx API documentation with dependent project inventories
* Create, increment and update Git tags
* Validate the change log and Git tag versions are in sync.
* Incorporate custom [jinja2] templates to amend the `pyproject.toml` file
  creation (see [Templating](#templating)).
* Render templates using the project's build information.
* Environment distribution feature to shore up some of the limitations of
  [pixi-pack].


## Documentation

See the [full documentation](https://plandes.github.io/relpo/index.html).
The [API reference](https://plandes.github.io/relpo/api.html) is also
available.


## Obtaining

The library can be installed with pip from the [pypi] repository:
```bash
pip3 install zensols.relpo
```


## Usage

The program is standalone, but needs template files to create the
`pyproject.toml` file.  The easiest way to do that is to use [zenbuild], which
has them.  This process needs [GNU make] for build automation.

1. Create a `relpo.yml` file (see [Configuration File](#configuration-file) and
   [example relpo.yml]).
1. Add source to `src/<organization name>/<project name>`
1. Add unit tests to `tests`
1. Add a `makefile` (see [makefile](#makefile))
1. Add git: `git init .`
1. Add the build sub: `git submodule add https://github.com/plandes/zenbuild`
1. Add a minimal change log: `echo "## [0.0.1] - $(date +%Y-%m-%d)" > CHANGELOG.md`
   (see [Keep a Changelog])
1. Write the `README.md` or a placeholder: `touch README.md`
1. Create the `pyproject.toml` file and [pixi] environments: `make pyinit`


### Configuration File

A minimal `relpo.yml` file is given below.  The file has everything needed to
create the standard `project` section of a `pyproject.toml` file, and the
sections needed by [pixi].  Additional `build` and `doc` top level mappings can
add to the `pyproject.toml` file creation and Sphinx API documentation (see
[example relpo.yml]).

```yaml
# author full name and email
author:
  name: <first> <last>
  email: email@example.com
# GitHub user name
github:
  user: exghuser
# 'project' section metadata
project:
  # company or organization name
  domain: acme
  # project name
  name: anvil
  # project documentation
  short_description: A short description
  long_description: >-
    Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod
    tempor incididunt ut labore et dolore magna aliqua.
  # keywords used in the package metadata
  keywords:
    - file
    - utility
  # Python version and dependencies
  python:
    # Python interpreter versions
    version:
      # constraint on install eligibility
      required: '>=3.11,<3.13'
      # last supported version of Python supported for the project
      previous: '3.11.12'
      # Python version supported for current development
      current: '3.12.10'
      # version of Python used to build/link specific to the host
      package_host: '3.11.6'
    # pypi dependencies added to 'project'
    dependencies:
      # cli
      - plac
```


### Makefile

Project makefiles that use [zenbuild] have the minimal form:

```makefile
## Build system
#
#
# type of project
PROJ_TYPE =         python
PROJ_MODULES =      python/doc git


## Includes
#
include ./zenbuild/main.mk
```


### Templating

Build automation tasks often use the project's configuration.  You can retrieve
project info using the program with [jinja2] templates.  For example, to output
the author's name as configured in the `relpo.yml` file:

```bash
cmd="relpo template --config relpo.yml,zenbuild/src/template/relpo/build.yml"
echo "author: {{ config.author.name }}" | $cmd
```


## Environemnt

The `envdist` action of the program to create an environment distribution tar
ball was added because [pixi-pack] currently lacks the functionality to deal
with PyPi source distributions.  The `envdist` feature creates a distribution
file that is deployed to a new environment and then installed as an
environment.


### Configuration

To create a distribution, first add the following entry to the `relpo.yml`
file:

```yaml
envdist:
  # the directory to cache conda and PyPi library files (usually '~/.cache/relpo')
  cache_dir: ~/.cache/relpo
  # the Pixi lock file (usually 'pixi.lock')
  pixi_lock_file: pixi.lock
  # the environment to export (i.e. 'default', 'testcur')
  environment: build-env
  # the platforms to export, or all if not provided (i.e. 'linux-64')
  #platforms: [linux-64, osx-64]
  # local files to add to the distribution
  injects:
    all:
      - pypi: target/dist/*.whl
```


### Usage

Then compile the wheel in `target/dist`, which is done with the `pywheel`
target when using [zenbuild].  Next create the environment tarball:

```bash
relpo envdist --config relpo.yml -o someproj.tar
```

Upload the tarball to the target machine and install it.

```bash
./<arch>-install.sh
```

This will install only the local artifacts taken from the `pixi.lock` file and
install them.  If your project has only Pypi wheels the entire environment is
installed with conda with a command equivalent to:

```bash
conda env create -f <arch>-environment.yml
```

However, the pip packages are installed as a separate command since conda
chokes on tarball dependencies (compare to the limitations of [pixi-pack]).


### Setuptools

If you have a project that adds tarball dependencies you may need to add
`setuptools` and/or `setuptools_scm` to the distribution.  That is done by
adding the following to the `relpo.yml` file:

```yaml
build:
  table_appends:
    tool.pixi.environments.build-env-add-setup:
      features: ['pyvercur', 'build-env-add-setup']
      solve-group: 'default'
    tool.pixi.feature.build-env-add-setup.dependencies:
      setuptools: '<81'
      setuptools_scm: '*'
      pip: '*'
envdist:
  environment: build-env-add-setup
```

This configuration tells `relpo` to add any version less than 81 of
`setuptools` and any version of `setuptools_scm`.  The latter is needed in
cases where a tarball has a `setup.py` configuration that lacks a version, and
instead, uses `use_scm_version=True`.  In these cases, the tar ball is
configured to defer to the version in the repository, which of course is not
available at the time of install in an environment with no internet connection.


## Changelog

An extensive changelog is available [here](CHANGELOG.md).


## Community

Please star this repository and let me know how and where you use this API.
Contributions as pull requests, feedback and any input is welcome.


## License

[MIT License](LICENSE.md)

Copyright (c) 2025 Paul Landes


<!-- links -->
[pypi]: https://pypi.org/project/zensols.relpo/
[pypi-link]: https://pypi.python.org/pypi/zensols.relpo
[pypi-badge]: https://img.shields.io/pypi/v/zensols.relpo.svg
[python314-badge]: https://img.shields.io/badge/python-3.14-blue.svg
[python314-link]: https://www.python.org/downloads/release/python-3140
[python313-badge]: https://img.shields.io/badge/python-3.13-blue.svg
[python313-link]: https://www.python.org/downloads/release/python-3130
[build-badge]: https://github.com/plandes/relpo/workflows/CI/badge.svg
[build-link]: https://github.com/plandes/relpo/actions

[pixi]: https://pixi.sh
[jinja2]: https://jinja.palletsprojects.com/en/stable/
[GNU make]: https://www.gnu.org/software/make/
[Keep a Changelog]: http://keepachangelog.com/
[zenbuild]: https://github.com/plandes/zenbuild
[example relpo.yml]: test-resources/relpo.yml
[pixi-pack]: https://github.com/Quantco/pixi-pack
