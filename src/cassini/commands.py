#!env python3
#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#
import asyncio
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from cassini.exceptions import PrintError, PrintersError, UploadError
from cassini.saturn_printer import CurrentStatus, FileStatus, PrintInfoStatus, SaturnPrinter
from cassini.simple_http_server import SimpleHTTPServer
from cassini.simple_mqtt_server import SimpleMQTTServer
from cassini.utils import get_printers

try:
    __version__ = version("cassini")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"


async def create_mqtt_server():
    mqtt = SimpleMQTTServer("127.0.0.1", 0)
    await mqtt.start()
    mqtt_server_task = asyncio.create_task(mqtt.serve_forever())
    return mqtt, mqtt.port, mqtt_server_task


async def create_http_server():
    http = SimpleHTTPServer("127.0.0.1", 0)
    await http.start()
    http_server_task = asyncio.create_task(http.serve_forever())
    return http, http.port, http_server_task


def do_status(printers: list[SaturnPrinter]) -> Table:
    table = Table(
        title="Status",
        show_header=False,
    )
    for p in printers:
        p.refresh()
        attrs = p.desc["Data"]["Attributes"]
        status = p.desc["Data"]["Status"]
        print_info = status["PrintInfo"]
        file_info = status["FileTransferInfo"]

        table.add_column("", style="green", justify="right")
        table.add_column("", style="cyan", justify="left")

        table.add_row("IP address", f"{p.addr[0]}")
        table.add_row(f"{attrs['Name']}", f"{attrs['MachineName']}")
        table.add_row("Machine Status:", f"{CurrentStatus(status['CurrentStatus']).name}")
        table.add_row("Print Status:", f"{PrintInfoStatus(print_info['Status']).name}")
        table.add_row("Layers:", f"{print_info['CurrentLayer']}/{print_info['TotalLayer']}")
        table.add_row("File:", f"{print_info['Filename']}")
        table.add_row("File Transfer Status:", f"{FileStatus(file_info['Status']).name}")
    return table


def live_status(printers: list[SaturnPrinter]):
    for p in printers:
        p.refresh()
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
        table.add_row(f"{attrs['Name']}", f"{attrs['MachineName']}")
        table.add_row("Machine Status:", f"{CurrentStatus(status['CurrentStatus']).name}")
        table.add_row("Print Status:", f"{PrintInfoStatus(print_info['Status']).name}")
        table.add_row("Layers:", f"{print_info['CurrentLayer']}/{print_info['TotalLayer']}")
        table.add_row("File:", f"{print_info['Filename']}")
        table.add_row("File Transfer Status:", f"{FileStatus(file_info['Status']).name}")

    return table


def do_status_full(printers: list[SaturnPrinter]) -> None:
    for p in printers:
        console = Console()
        console.print_json(data=p.desc)


def do_watch(
    printer_addr: SaturnPrinter,
    interval: int = 5,
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
            status = printer.status()
            pct = status["currentLayer"] / status["totalLayers"]
            progress.update(task, advance=status["currentLayer"] - previous_layer, completed=status["currentLayer"])
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


async def do_upload(printer: SaturnPrinter, filename: Path):
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

    upload_task = asyncio.create_task(printer.upload_file(filename))
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


def find_printer_addr(broadcast="<broadcast>") -> str:
    printers = get_printers(broadcast=broadcast)
    match len(printers):
        case 1:
            printer_addr = printers[0].addr[0]
            logger.info(f"Printer found at {printer_addr}")
        case 0:
            msg = "Unable to automatically printers on the network. Try specifying the printer's IP address"
            raise PrintersError(msg)
        case _:
            msg = (
                f"{len(printers)} were found, and `watch` is currently only capable of monitoring one "
                f"printer at a time. Please specify the desired printer's IP address"
            )
            raise PrintersError(msg)
    return printer_addr
