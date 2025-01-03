#!env python3
#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#
import asyncio
import contextlib
import socket
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger
from rich import print as rprint
from rich.console import Console
from rich.live import Live

from cassini.commands import do_print, do_status, do_status_full, do_upload, do_watch, live_status
from cassini.logging import init_logger
from cassini.saturn_printer import SaturnPrinter
from cassini.utils import find_printer_addr, get_printers

try:
    __version__ = version("cassini")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"


class PrintError(Exception):
    pass


class UploadError(Exception):
    pass


class PrintersError(Exception):
    pass


cassini = typer.Typer(
    name="cassini",
    short_help="ELEGOO Saturn printer control utility",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    rich_help_panel=True,
)

verbosity_level = 0


@cassini.callback()
def version_callback(
    version: Annotated[
        bool,
        typer.Option(
            "-v",
            "--version",
            help="Show Cassini version",
        ),
    ] = False,
) -> None:  # FBT001
    """Prints the version of the package."""
    if version:
        rprint(f"[yellow]cassini[/] version: [bold blue]{__version__}[/]")
        raise typer.Exit()


@cassini.callback()
def verbosity(
    verbose: Annotated[
        int,
        typer.Option(
            "-l",
            "--verbose",
            help="Control output verbosity. Pass this argument multiple times to increase the amount of output.",
            count=True,
        ),
    ] = 0,
    version: Annotated[
        bool, typer.Option("-v", "--version", help="Show Cassini version", callback=version_callback)
    ] = False,
) -> None:
    verbosity_level = verbose  # noqa: F841


@cassini.command(help="Discover and display status of all printers")
def status(
    printer: Annotated[str | None, typer.Argument(help="ID of printer to target")] = None,
    broadcast: Annotated[str, typer.Option("--broadcast", help="Explicit broadcast IP address")] = "<broadcast>",
    status_full: Annotated[
        bool, typer.Option("--full", help="Discover and display full status of all printers")
    ] = False,
    live_update: Annotated[bool, typer.Option("--live", help="Update the status table in read time.")] = False,
    update_interval: Annotated[int, typer.Option("--interval", help="Live update interval, in seconds.")] = 1,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    version: Annotated[
        bool, typer.Option("--version", help="Show version", callback=version_callback, is_eager=True)
    ] = False,
):
    if debug:
        init_logger(3)
    if printer:
        printers = get_printers(printer=printer)
    else:
        printers = get_printers(broadcast=broadcast)
    console = Console()
    if live_update:
        with Live(live_status(printers), console=console, refresh_per_second=4, transient=False, screen=False) as live:
            while True:
                time.sleep(update_interval)
                live.update(do_status(printers))
    elif status_full:
        console.print(do_status_full(printers))
    else:
        console.print(do_status(printers))


@cassini.command(help="Continuously update the status of the selected printer")
def watch(
    printer_addr: Annotated[str | None, typer.Argument(help="ID of printer to target")] = None,
    interval: Annotated[int, typer.Option("--interval", help="Status update interval (seconds)")] = 5,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    version: Annotated[
        bool, typer.Option("--version", help="Show version", callback=version_callback, is_eager=True)
    ] = False,
):
    if debug:
        init_logger(3)
    printer_addr = find_printer_addr() if printer_addr is None else printer_addr
    do_watch(printer_addr, interval=interval)


@cassini.command(help="Upload a file to the printer")
def upload(
    filename: Annotated[Path, typer.Argument(help="File to upload")],
    printer_addr: Annotated[str | None, typer.Argument(help="ID of printer to target")] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    version: Annotated[
        bool, typer.Option("--version", help="Show version", callback=version_callback, is_eager=True)
    ] = False,
):
    if debug:
        init_logger(3)
    printer_addr = find_printer_addr() if printer_addr is None else printer_addr
    printer = SaturnPrinter().find_printer(addr=printer_addr)
    logger.info(f"Printer: {printer.describe()} ({printer.addr[0]})")

    if printer.busy:
        msg = f"Printer is busy (status: {printer.current_status})"
        logger.error(msg)
        raise PrintError(msg)
    else:
        asyncio.run(do_upload(printer, filename))


@cassini.command(name="print", help="Start printing a file already present on the printer")
def print_file(
    filename: Annotated[str, typer.Argument(help="File to print")],
    printer_addr: Annotated[str | None, typer.Argument(help="ID of printer to target")] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    version: Annotated[
        bool, typer.Option("--version", help="Show version", callback=version_callback, is_eager=True)
    ] = False,
):
    if debug:
        init_logger(3)
    printer_addr = find_printer_addr() if printer_addr is None else printer_addr
    printer = SaturnPrinter().find_printer(addr=printer_addr)
    logger.info(f"Printer: {printer.describe()} ({printer.addr[0]})")
    if printer.busy:
        msg = f"Printer is busy (status: {printer.current_status})"
        logger.error(msg)
        raise PrintError(msg)
    else:
        asyncio.run(do_print(printer, filename))


@cassini.command(help="Connect printer to particular MQTT server")
def connect_mqtt(
    address: Annotated[str, typer.Argument(help='MQTT host and port, e.g. "192.168.1.33:1883" or "mqtt.local:1883"')],
    printer: Annotated[str | None, typer.Option("--printer", help="ID of printer to target")] = None,
    broadcast: Annotated[str | None, typer.Option("--broadcast", help="Explicit broadcast IP address")] = None,
    debug: Annotated[bool, typer.Option("--debug")] = False,
    version: Annotated[
        bool, typer.Option("--version", help="Show version", callback=version_callback, is_eager=True)
    ] = False,
):
    if debug:
        init_logger(3)
    printers = get_printers(printer, broadcast)

    mqtt_host, mqtt_port = address.split(":")
    with contextlib.suppress(socket.gaierror):
        mqtt_host = socket.gethostbyname(mqtt_host)
    for p in printers:
        p.connect_mqtt(mqtt_host, mqtt_port)


if __name__ == "main":
    cassini()
