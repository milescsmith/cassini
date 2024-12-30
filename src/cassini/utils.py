from loguru import logger

from cassini.exceptions import PrintersError
from cassini.saturn_printer import SaturnPrinter


def get_printers(
    printer: str | None = None,
    broadcast: str = "<broadcast>",
):
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
