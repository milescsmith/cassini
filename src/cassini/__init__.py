"""
.. module:: cassini
   :platform: Unix, Windows
   :synopsis: Interact with ELEGOO printers

.. moduleauthor:: Vladimir Vukicevic <{{email}}>
"""


from loguru import logger

from cassini.cassini import __version__, connect_mqtt, get_printers, print_file, status, upload, watch

logger.disable("cassini")

__all__ = [
    "__version__",
    "status",
    "watch",
    "upload",
    "print_file",
    "get_printers",
    "connect_mqtt",
]
