# Changelog

## [2.0.1]

### Fixed

- That damned inability of MQTT to work with anything other than `host="0.0.0.0"` bites me again


## [2.0.0]

### Added

- Incorporated code from the [Resin Print Portal (RPP)](https://github.com/jjtronics/RPP) project.
    - Added running RPP via Waitress as a server

### Changed

- Increased Typer required version to allow for newer Union types
- Unified passing the printer's IP address as an argument or option (i.e. do
you have to put `--printer` before the address?)
    - Passing the IP address is now optional as long as there is just one printer
        on the network
- Reorganized module structure, separating the CLI commands from the underlying 
    functions they call
- 

## [1.5.0] - 2024-07-30

### Fixed

- Undid a bug introduced in 1.3.0 where the MQTT server was set to listen only on localhost instead of 0.0.0.0, which
    meant that any transfers would just timeout
- Removed the "start_printing" argument from any and all of the upload functions since it was unused and only caused 
    problems

## [1.4.0] - 2024-07-26

### Added

- Pre-commit and other elements to bring this in line with general modernizing efforts

## [1.3.0] - 2024-07-13

### Added

- added the `--live` option to `cassini.cassini.status` to allow for a persistent table that updates in realtime
- added a draft of a `Printer` abstract base class to help others with extending cassini beyond Saturn printers

## [1.2.0] - 2024-07-10

### Added

- Added a `Printer` abstract base class so there's a defined interface for extending cassini to printers beyond the Saturn 3

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

[2.0.1]: https://github.com/milescsmith/cassini/compare/2.0.0..2.0.1
[2.0.0]: https://github.com/milescsmith/cassini/compare/1.5.0..2.0.0
[1.5.0]: https://github.com/milescsmith/cassini/compare/1.4.0..1.5.0
[1.4.0]: https://github.com/milescsmith/cassini/compare/1.3.0..1.4.0
[1.3.0]: https://github.com/milescsmith/cassini/compare/1.2.0..1.3.0
[1.2.0]: https://github.com/milescsmith/cassini/compare/1.1.0..1.2.0
[1.1.0]: https://github.com/milescsmith/cassini/compare/1.0.0..1.1.0
[1.0.0]: https://github.com/milescsmith/cassini/tag/1.0.0
