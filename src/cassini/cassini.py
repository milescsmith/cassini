#!env python3
#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#
import asyncio
import pprint
import socket
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Annotated, Optional

import typer
from loguru import logger
from rich import print as rprint
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    # RenderableColumn,
    # SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from cassini.logging import init_logger
from cassini.saturn_printer import CurrentStatus, FileStatus, PrintInfoStatus, SaturnPrinter
from cassini.simple_http_server import SimpleHTTPServer
from cassini.simple_mqtt_server import SimpleMQTTServer

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"

class PrintError(Exception):
    pass

class UploadError(Exception):
    pass

app = typer.Typer(
    name="cassini",
    short_help="ELEGOO Saturn printer control utility",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)

verbosity_level = 0

def version_callback(value: bool) -> None: # FBT001
    """Prints the version of the package."""
    if value:
        rprint(f"[yellow]boardgamegeek[/] version: [bold blue]{__version__}[/]")
        raise typer.Exit()


@app.callback()
def verbosity(
    verbose: Annotated[
        int,
        typer.Option(
            "-v",
            "--verbose",
            help="Control output verbosity. Pass this argument multiple times to increase the amount of output.",
            count=True,
        ),
    ] = 0
) -> None:
    verbosity_level = verbose  # noqa: F841


async def create_mqtt_server():
    mqtt = SimpleMQTTServer("0.0.0.0", 0)
    await mqtt.start()
    mqtt_server_task = asyncio.create_task(mqtt.serve_forever())
    return mqtt, mqtt.port, mqtt_server_task


async def create_http_server():
    http = SimpleHTTPServer("0.0.0.0", 0)
    await http.start()
    http_server_task = asyncio.create_task(http.serve_forever())
    return http, http.port, http_server_task


def do_status(printers: list[SaturnPrinter]):
    for p in printers:
        attrs = p.desc["Data"]["Attributes"]
        status = p.desc["Data"]["Status"]
        print_info = status["PrintInfo"]
        file_info = status["FileTransferInfo"]
        table = Table(
            title="Status",
            show_header=False,
            )

        table.add_column("", style="green", justify="right")
        table.add_column("", style="cyan", justify="left")

        table.add_row("IP address", f"{p.addr[0]}")
        table.add_row(f"{attrs['Name']}",f"{attrs['MachineName']}")
        table.add_row("Machine Status:",f"{CurrentStatus(status['CurrentStatus']).name}")
        table.add_row("Print Status:",f"{PrintInfoStatus(print_info['Status']).name}")
        table.add_row("Layers:",f"{print_info['CurrentLayer']}/{print_info['TotalLayer']}")
        table.add_row("File:",f"{print_info['Filename']}")
        table.add_row("File Transfer Status:",f"{FileStatus(file_info['Status']).name}")
        console = Console()
        console.print(table)


def do_status_full(printers: list[SaturnPrinter]):
    for p in printers:
        pprint.pprint(p.desc)


def do_watch(
    printer_addr: SaturnPrinter,
    interval: int=5,
    ):
    printer = SaturnPrinter().find_printer(addr=printer_addr)
    status = printer.status()
    previous_layer = 0
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task(description=f"Printing {status['filename']}", total=status["totalLayers"])
        progress.start()
        while True:
            # printer_addr is not an optional argument, so there's no need to search for all the printers
            # printers = SaturnPrinter.find_printers(broadcast=broadcast)
            # if len(printers) > 1:
            printer = SaturnPrinter().find_printer(addr=printer_addr)
            status = printer.status() # I guess we really need an `update_status` method
            pct = status["currentLayer"] / status["totalLayers"]
            progress.update(task, advance=status["currentLayer"]-previous_layer, completed=status["currentLayer"])
            if pct >= 1.0:
                break
            previous_layer = status["currentLayer"]
            time.sleep(interval)


async def create_servers():
    mqtt, *_ = await create_mqtt_server()
    http, *_ = await create_http_server()

    return mqtt, http


async def do_print(printer, filename):
    mqtt, http = await create_servers()
    connected = await printer.connect(mqtt, http)
    if not connected:
        msg = "Failed to connect to printer"
        logger.error(msg)
        raise ConnectionError(msg)

    result = await printer.print_file(filename)
    if result:
        logger.info("Print started")
    else:
        msg = "Failed to start print"
        logger.error(msg)
        raise PrintError(msg)


async def do_upload(
    printer: SaturnPrinter,
    filename: Path,
    start_printing=False
    ):
    if not Path(filename).exists():
        msg = f"{filename} does not exist"
        logger.error(msg)
        raise FileNotFoundError(msg)

    mqtt, http = await create_servers()
    connected = await printer.connect(mqtt, http)
    if not connected:
        msg = "Failed to connect to printer"
        logger.error(msg)
        raise ConnectionError(msg)

    # await printer.upload_file(filename, start_printing=start_printing)
    upload_task = asyncio.create_task(printer.upload_file(filename, start_printing=start_printing))
    # grab the first one, because we want the file size
    basename = filename.name
    file_size = filename.stat().st_size
    with Progress() as progress:
        task = progress.add_task(description=basename, total=file_size)
        while True:
            if printer.file_transfer_future is None:
                await asyncio.sleep(0.1)
                continue
            print_progress = await printer.file_transfer_future
            if print_progress[0] < 0:
                msg = "File upload failed!"
                logger.error(msg)
                raise UploadError(msg)
            progress.update(task, advance=print_progress[0])
            if print_progress[0] >= print_progress[1]:
                break
    await upload_task


def get_printers(printer: Optional[str] = None, broadcast: str = "<broadcast>",):
    if printer:
        printer = SaturnPrinter().find_printer(addr=printer)
        if printer is None:
            logger.error(f"No response from printer {printer}")
        printers = [printer]
    else:
        printers = SaturnPrinter().find_printers(broadcast=broadcast)
        if len(printers) == 0:
            logger.error("No printers found on network")
    return printers


@app.command(help="Discover and display status of all printers")
def status(
    printer: Annotated[Optional[str], typer.Argument(help="ID of printer to target")] = None,
    broadcast: Annotated[str, typer.Option(help="Explicit broadcast IP address")] = "<broadcast>",
    status_full: Annotated[bool, typer.Option(help="Discover and display full status of all printers")] = False,
    debug: Annotated[
        bool,
        typer.Option("--debug")
    ] = False,
):
    if debug:
        init_logger(3)
    if printer:
        printers = get_printers(printer=printer)
    else:
        printers = get_printers(broadcast=broadcast)
    if status_full:
        do_status_full(printers)
    else:
        do_status(printers)


@app.command(help="Continuously update the status of the selected printer")
def watch(
    printer_addr: Annotated[Optional[str], typer.Option("--printer",help="ID of printer to target")] = None,
    interval: Annotated[int, typer.Option("--interval", help="Status update interval (seconds)")] = 5,
    debug: Annotated[
        bool,
        typer.Option("--debug")
    ] = False,
):
    if debug:
        init_logger(3)
    do_watch(printer_addr, interval=interval)

@app.command(help="Upload a file to the printer")
def upload(
    filename: Annotated[Path, typer.Argument(help="File to upload")],
    printer_addr: Annotated[str, typer.Argument(help="ID of printer to target")],
    start_printing: Annotated[bool, typer.Option("--start-printing", help="Start printing after upload is complete")] = True,
    debug: Annotated[
        bool,
        typer.Option("--debug")
    ] = False,
):
    if debug:
        init_logger(3)
    printer = SaturnPrinter().find_printer(addr=printer_addr)
    logger.info(f"Printer: {printer.describe()} ({printer.addr[0]})")
    if printer.busy:
        msg = f"Printer is busy (status: {printer.current_status})"
        logger.error(msg)
        raise PrintError(msg)
    else:
        asyncio.run(do_upload(printer, filename, start_printing=start_printing))

@app.command(help="Start printing a file already present on the printer")
def print_file(
    filename: Annotated[str, typer.Argument(help="File to print")],
    printer_addr: Annotated[str, typer.Argument(help="ID of printer to target")],
    debug: Annotated[
        bool,
        typer.Option("--debug")
    ] = False,
):
    if debug:
        init_logger(3)
    printer = SaturnPrinter().find_printer(addr=printer_addr)
    logger.info(f"Printer: {printer.describe()} ({printer.addr[0]})")
    if printer.busy:
        msg = f"Printer is busy (status: {printer.current_status})"
        logger.error(msg)
        raise PrintError(msg)
    else:
        asyncio.run(do_print(printer, filename))

@app.command(help="Connect printer to particular MQTT server")
def connect_mqtt(
    address: Annotated[str, typer.Argument(help='MQTT host and port, e.g. "192.168.1.33:1883" or "mqtt.local:1883"')],
    printer: Annotated[Optional[str], typer.Option("--printer",help="ID of printer to target")] = None,
    broadcast: Annotated[Optional[str], typer.Option("--broadcast", help="Explicit broadcast IP address")] = None,
    debug: Annotated[
        bool,
        typer.Option("--debug")
    ] = False,
):
    if debug:
        init_logger(3)
    printers = get_printers(printer, broadcast)

    mqtt_host, mqtt_port = address.split(":")
    try:
        mqtt_host = socket.gethostbyname(mqtt_host)
    except socket.gaierror:
        pass
    for p in printers:
        p.connect_mqtt(mqtt_host, mqtt_port)

if __name__ == "main":
    app()
