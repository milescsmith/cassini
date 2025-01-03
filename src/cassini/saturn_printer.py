#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#

import asyncio
import json
import secrets

# import random
import socket
import sys
import time
from enum import IntEnum
from pathlib import Path
from typing import Final

from loguru import logger

from cassini.printer import Printer

SATURN_UDP_PORT: Final[int] = 3000
TOO_MANY_STATUS_REPLIES: Final[int] = 5


# CurrentStatus field inside Status
class CurrentStatus(IntEnum):
    READY = 0
    BUSY = 1  # Printer might be sitting at the "Completed" screen
    # SATURN_STATUS_BUSY_2 = 1 # post-HEAD call on file transfer, along with SATURN_FILE_STATUS = 3 on error, and 2 on completion


# Status field inside PrintInfo
class PrintInfoStatus(IntEnum):
    # TODO: double check these
    NOTPRINTING = 0
    STARTINGPRINT = 1
    EXPOSURE = 2
    RETRACTING = 3
    LOWERING = 4
    FINISHED = 12  # I guess? This is the status I get at the end of a print but not sure how it differs from 16
    COMPLETE = 16  # pretty sure this is correct


# Status field inside FileTransferInfo
class FileStatus(IntEnum):
    NONE = 0
    DONE = 2
    ERROR = 3


class Command(IntEnum):
    CMD_0 = 0  # null data
    CMD_1 = 1  # null data
    DISCONNECT = 64  # Maybe disconnect?
    START_PRINTING = 128  # "Filename": "X", "StartLayer": 0
    UPLOAD_FILE = 256  # "Check": 0, "CleanCache": 1, "Compress": 0, "FileSize": 3541068, "Filename": "_ResinXP2-ValidationMatrix_v2.goo", "MD5": "205abc8fab0762ad2b0ee1f6b63b1750", "URL": "http://${ipaddr}:58883/f60c0718c8144b0db48b7149d4d85390.goo" },
    SET_MYSTERY_TIME_PERIOD = 512  # "TimePeriod": 5000


def random_hexstr():
    return f"{secrets.randbits(128):032x}"


# TODO: feels like we should change the desc member to either a namedtuple or dataclass
class SaturnPrinter(Printer):
    def __init__(self, addr=None, desc=None, timeout=5):
        self.addr = addr
        self.timeout = timeout
        self.file_transfer_future = None
        if desc is not None:
            self.set_desc(desc)
        else:
            self.desc = None

    # Broadcast and find all printers, return array of SaturnPrinter objects
    @classmethod
    def find_printers(cls, timeout=1, broadcast=None):
        if broadcast is None:
            broadcast = "<broadcast>"
        printers = []
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sock:
            sock.settimeout(timeout)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, timeout)
            sock.sendto(b"M99999", (broadcast, SATURN_UDP_PORT))

            now = time.time()
            while not time.time() - now > timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                except TimeoutError:
                    continue
                else:
                    # logger.debug(f'Found printer at {addr}')
                    pdata = json.loads(data.decode("utf-8"))
                    printers.append(cls(addr=addr, desc=pdata))
        return printers

    # Find a specific printer at the given address, return a SaturnPrinter object
    # or None if no response is obtained
    @classmethod
    def find_printer(cls, addr: str):
        sp = cls()
        printers = sp.find_printers(broadcast=addr)
        if len(printers) == 0 or printers[0].addr[0] != addr:
            return None
        return printers[0]

    # Refresh this SaturnPrinter with latest status
    def refresh(self, timeout=5):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sock:
            sock.settimeout(timeout)
            sock.sendto(b"M99999", self.addr)
            try:
                data, addr = sock.recvfrom(1024)
            except TimeoutError:
                return False
            else:
                pdata = json.loads(data.decode("utf-8"))
                self.set_desc(pdata)

    def set_desc(self, desc):
        self.desc = desc
        self.id = desc["Data"]["Attributes"]["MainboardID"]
        self.name = desc["Data"]["Attributes"]["Name"]
        self.machine_name = desc["Data"]["Attributes"]["MachineName"]
        self.current_status = desc["Data"]["Status"]["CurrentStatus"]
        self.busy = self.current_status > 0

    # Tell this printer to connect to the specified mqtt and http
    # servers, for further control
    async def connect(self, mqtt, http):
        self.mqtt = mqtt
        self.http = http

        # Tell the printer to connect
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with sock:
            sock.sendto(b"M66666 " + str(mqtt.port).encode("utf-8"), self.addr)

        # wait for the connection
        client_id = await asyncio.wait_for(mqtt.client_connection, timeout=self.timeout)
        if client_id != self.id:
            logger.error(f"Client ID mismatch: {client_id} != {self.id}")
            return False

        # wait for the client to subscribe to the request topic
        topic = await asyncio.wait_for(self.mqtt.client_subscribed, timeout=self.timeout)
        logger.debug(f"Client subscribed to {topic}")

        await self.send_command_and_wait(Command.CMD_0)
        await self.send_command_and_wait(Command.CMD_1)
        await self.send_command_and_wait(Command.SET_MYSTERY_TIME_PERIOD, {"TimePeriod": 5000})

        return True

    async def disconnect(self):
        await self.send_command_and_wait(Command.DISCONNECT)

    async def upload_file(self, filename: Path):
        try:
            await self.upload_file_inner(filename)
        except Exception as ex:
            logger.error(f"Exception during upload: {ex}")
            self.file_transfer_future.set_result((-1, -1, filename))
            self.file_transfer_future = asyncio.get_running_loop().create_future()

    async def upload_file_inner(self, filename: Path):
        # schedule a future that can be used for status, in case this is kicked off as a task
        self.file_transfer_future = asyncio.get_running_loop().create_future()

        # get base filename and extension
        if isinstance(filename, str):
            basename = filename.split("\\")[-1].split("/")[-1]
            ext = basename.split(".")[-1].lower()
        elif isinstance(filename, Path):
            basename = filename.name.lstrip(".")
            ext = filename.suffix
        if ext not in ("ctb", "goo"):
            logger.warning(f"Unknown file extension: {ext}")

        httpname = f"{random_hexstr()}.{ext}"
        fileinfo = self.http.register_file_route(f"/{httpname}", filename)

        cmd_data = {
            "Check": 0,
            "CleanCache": 1,
            "Compress": 0,
            "FileSize": fileinfo["size"],
            "Filename": basename,
            "MD5": fileinfo["md5"],
            "URL": f"http://${{ipaddr}}:{self.http.port}/{httpname}",
        }

        await self.send_command_and_wait(Command.UPLOAD_FILE, cmd_data)

        # now process status updates from the printer
        while True:
            reply = await asyncio.wait_for(self.mqtt.next_published_message(), timeout=self.timeout * 2)
            data = json.loads(reply["payload"])
            if reply["topic"] == f"/sdcp/response/{self.id}":
                logger.warning(
                    f"Got unexpected RESPONSE (no outstanding request), topic: {reply['topic']} data: {data}"
                )
            elif reply["topic"] == f"/sdcp/status/{self.id}":
                self.incoming_status(data["Data"]["Status"])

                status = data["Data"]["Status"]
                file_info = status["FileTransferInfo"]
                current_offset = file_info["DownloadOffset"]
                total_size = file_info["FileTotalSize"]
                file_name = file_info["Filename"]

                # We assume that the printer immediately goes into BUSY status after it processes
                # the upload command
                if status["CurrentStatus"] == CurrentStatus.READY:
                    if file_info["Status"] == FileStatus.DONE:
                        self.file_transfer_future.set_result((total_size, total_size, file_name))
                    elif file_info["Status"] == FileStatus.ERROR:
                        logger.error("Transfer error!")
                        self.file_transfer_future.set_result((-1, total_size, file_name))
                    else:
                        logger.error(f"Unknown file transfer status code: {file_info['Status']}")
                        self.file_transfer_future.set_result((-1, total_size, file_name))
                    break

                self.file_transfer_future.set_result((current_offset, total_size, file_name))
                self.file_transfer_future = asyncio.get_running_loop().create_future()
            elif reply["topic"] != f"/sdcp/attributes/{self.id}":
                logger.warning(f"Got unknown topic message: {reply['topic']}")

        self.file_transfer_future = None

    async def send_command_and_wait(self, cmdid, data=None, abort_on_bad_ack=True):
        # Send the 0 and 1 messages
        req = self.send_command(cmdid, data)
        logger.debug(f"Sent command {cmdid} as request {req}")
        while True:
            reply = await asyncio.wait_for(self.mqtt.next_published_message(), timeout=self.timeout)
            data = json.loads(reply["payload"])
            if reply["topic"] == f"/sdcp/response/{self.id}":
                if data["Data"]["RequestID"] == req:
                    logger.debug(f"Got response to {req}")
                    result = data["Data"]["Data"]
                    if abort_on_bad_ack and result["Ack"] != 0:
                        logger.error(f"Got bad ack in response: {result}")
                        sys.exit(1)
                    return result
            elif reply["topic"] == f"/sdcp/status/{self.id}":
                self.incoming_status(data["Data"]["Status"])
            elif reply["topic"] != f"/sdcp/attributes/{self.id}":
                logger.warning(f"Got unknown topic message: {reply['topic']}")

    async def print_file(self, filename):
        cmd_data = {"Filename": filename, "StartLayer": 0}

        await self.send_command_and_wait(Command.START_PRINTING, cmd_data)

        # process status updates from the printer, enough to know whether printing
        # started or failed to start
        status_count = 0
        while True:
            reply = await asyncio.wait_for(self.mqtt.next_published_message(), timeout=self.timeout * 2)
            data = json.loads(reply["payload"])
            if reply["topic"] == f"/sdcp/response/{self.id}":
                logger.warning(
                    f"Got unexpected RESPONSE (no outstanding request), topic: {reply['topic']} data: {data}"
                )
            elif reply["topic"] == f"/sdcp/status/{self.id}":
                self.incoming_status(data["Data"]["Status"])
                status_count += 1

                status = data["Data"]["Status"]
                print_info = status["PrintInfo"]

                current_status = status["CurrentStatus"]
                print_status = print_info["Status"]

                if current_status == CurrentStatus.BUSY and print_status > 0:
                    return True

                logger.debug(status)
                logger.debug(print_info)

                if status_count >= TOO_MANY_STATUS_REPLIES:
                    logger.warning("Too many status replies without success or failure")
                    return False

            elif reply["topic"] != f"/sdcp/attributes/{self.id}":
                logger.warning(f"Got unknown topic message: {reply['topic']}")

    async def process_responses(self):
        while True:
            reply = await asyncio.wait_for(self.mqtt.next_published_message(), timeout=self.timeout)
            self.desc = json.loads(reply["payload"])

    def incoming_status(self, status):
        logger.debug(f"STATUS: {status}")

    def incoming_response(self, response_id, cmd, data):
        logger.debug(f"RESPONSE: {response_id} -- {cmd}: {data}")

    def describe(self):
        attrs = self.desc["Data"]["Attributes"]
        return f"{attrs['Name']} ({attrs['MachineName']})"

    def status(self):
        self.refresh()
        printinfo = self.desc["Data"]["Status"]["PrintInfo"]
        return {
            "status": self.desc["Data"]["Status"]["CurrentStatus"],
            "filename": printinfo["Filename"],
            "currentLayer": printinfo["CurrentLayer"],
            "totalLayers": printinfo["TotalLayer"],
        }

    def send_command(self, cmdid, data=None):
        # generate 16-byte random identifier as a hex string
        hexstr = random_hexstr()
        timestamp = int(time.time() * 1000)
        cmd_data = {
            "Data": {
                "Cmd": cmdid.value,
                "Data": data,
                "From": 0,
                "MainboardID": self.id,
                "RequestID": hexstr,
                "TimeStamp": timestamp,
            },
            "Id": self.desc["Id"],
        }
        self.mqtt.publish(f"/sdcp/request/{self.id}", json.dumps(cmd_data))
        return hexstr

    def connect_mqtt(self, mqtt_host, mqtt_port):
        """
        Connect printer to MQTT server

        It spoofs UDP packet to the printer to make it connect to particular MQTT server
        """
        # placing this inside the function because this is the only place these are used AND it slows down initialization
        from scapy.all import IP, UDP, send

        logger.getLogger("scapy.runtime").setLevel(logger.WARNING)
        ip = IP(dst=self.addr[0], src=mqtt_host)
        any_src_port = secrets.choice(range(1024, 65535))
        udp = UDP(sport=any_src_port, dport=SATURN_UDP_PORT)
        payload = f"M66666 {mqtt_port}"
        packet = ip / udp / payload
        send(packet)
