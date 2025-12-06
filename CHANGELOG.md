# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).


## [Unreleased]


## [0.0.9] - 2025-12-05
### Added
- Sphinx `sphinx-codeautolink` extension to create in-code links.


## [0.0.8] - 2025-11-21
### Added
- Enable `envdist` installations of projects that have tarball Pypi
  dependencies.

### Changed
- Allow replacement of tables in the `pyproject.toml` configuration.  This
  fixes the `key already exists` error by modifying inline tables in the
  `pyproject.toml` file.


## [0.0.7] - 2025-06-22
### Added
- Configuration to optionally generate the command-line entry points.


## [0.0.6] - 2025-06-22
### Added
- Version to the CLI.

### Changed
- Relax Python interpreter version to include 3.11 again, which is needed for
  builds.
- Fix log level debug trace.


## [0.0.5] - 2025-06-07
### Added
- Environment distribution feature to shore up some of the limitations of
  [pixi-pack].


## [0.0.4] - 2025-05-30
### Added
- A feature to append to `pyproject.toml` TOML tables.


## [0.0.3] - 2025-05-11
### Changed
- Build process.


## [0.0.2] - 2025-05-03
Release candidate


## [0.0.1] - 2025-05-02
### Added
- Initial version.


<!-- links -->
[Unreleased]: https://github.com/plandes/relpo/compare/v0.0.9...HEAD
[0.0.9]: https://github.com/plandes/relpo/compare/v0.0.8...v0.0.9
[0.0.8]: https://github.com/plandes/relpo/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/plandes/relpo/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/plandes/relpo/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/plandes/relpo/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/plandes/relpo/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/plandes/relpo/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/plandes/relpo/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/plandes/relpo/compare/v0.0.0...v0.0.1

[pixi-pack]: https://github.com/Quantco/pixi-pack
