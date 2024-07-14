#
# Cassini
#
# Copyright (C) 2023 Vladimir Vukicevic
# License: MIT
#
import asyncio
import hashlib
import os

from loguru import logger


class SimpleHTTPServer:
    BufferSize = 1024768

    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.server = None
        self.routes = {}

    def register_file_route(self, path, filename):
        size = os.path.getsize(filename)
        md5 = hashlib.md5()
        with open(filename, "rb") as f:
            while True:
                if data := f.read(1024):
                    md5.update(data)
                else:
                    break
        route = {"file": filename, "size": size, "md5": md5.hexdigest()}
        self.routes[path] = route
        return route

    def unregister_file_route(self, path):
        del self.routes[path]

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self.port = self.server.sockets[0].getsockname()[1]
        logger.debug(f"HTTP Listening on {self.server.sockets[0].getsockname()}")

    async def serve_forever(self):
        await self.server.serve_forever()

    async def handle_client(self, reader, writer):
        try:
            await self.handle_client_inner(reader, writer)
        except Exception as e:
            logger.error(f"HTTP Exception handling client: {e}")

    async def handle_client_inner(self, reader, writer):
        logger.debug(f"HTTP connection from {writer.get_extra_info('peername')}")
        data = b""
        while True:
            data += await reader.read(1024)
            if b"\r\n\r\n" in data:
                break

        logger.debug(f"HTTP request: {data}")
        request_line = data.decode().splitlines()[0]
        method, path, _ = request_line.split()

        if path not in self.routes:
            logger.debug(f"HTTP path {path} not found in routes")
            logger.debug(self.routes)
            writer.write(b"HTTP/1.1 404 Not Found\r\n")
            writer.close()
            return

        route = self.routes[path]
        logger.debug(f"HTTP method {method} path {path} route: {route}")

        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Etag: {route['md5']}\r\n"
            f"Content-Length: {route['size']}\r\n"
            "\r\n"
        )

        logger.debug(f"Writing header:\n{header}")
        writer.write(header.encode())

        if method == "GET":
            total = 0
            with open(route["file"], "rb") as f:
                while True:
                    data = f.read(self.BufferSize)
                    if not data:
                        break
                    writer.write(data)
                    logger.debug(f"HTTP wrote {len(data)} bytes")
                    # await asyncio.sleep(1)
                    total += len(data)
            logger.debug(f"HTTP wrote total {total} bytes")

        await writer.drain()
        writer.close()
        await writer.wait_closed()
        logger.debug("HTTP connection closed")
