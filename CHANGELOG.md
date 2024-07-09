# Changelog

## [1.1.0] - 2024-07-08

### Fixed

- Fixed the `SaturnPrinter.refresh()` method

### Changed

- The `SaturnPrinter.status()` method now refresh before printing the statsu

## [1.0.0] - 2024-07-07

### Changed

- Reformatted into an installable module via [`PDM`](https://pdm-project.org/)
- Replace use of `argparse` with [`typer`](https://typer.tiangolo.com/)
- Replace use of `alive-progress` with [`rich.progress`](https://rich.readthedocs.io/en/stable/progress.html)
- Replace direct use of the `logging` module with [`loguru`](https://loguru.readthedocs.io/)
- Reformatted the output from `cassini.status` to use `rich.table`
- Multiple `Enum` changed to `IntEnum`

### Fixed
- changed `cassini.SaturnPrinter.find_printer` and `cassini.SaturnPrinter.find_printers` to classmethods

### Added
- linting via ruff
- Some typing (with a lot left to go)


[1.0.0]: https://github.com/milescsmith/pyplier/tag/1.0.0
