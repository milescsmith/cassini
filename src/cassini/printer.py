from abc import ABC, abstractmethod


class Printer(ABC):
    """
    Abstract class that represents a resin 3D printer
    """

    @abstractmethod
    def refresh(self):
        pass

    @abstractmethod
    def set_desc(self, desc):
        pass

    @abstractmethod
    async def connect(self, mqtt, http):
        pass

    @abstractmethod
    async def disconnect(self):
        pass

    @abstractmethod
    async def upload_file(self, filename, start_printing=False):
        pass

    @abstractmethod
    def status(self):
        pass

    @abstractmethod
    def describe(self):
        pass

    @abstractmethod
    def send_command(self, cmdid, data):
        pass

    @abstractmethod
    async def print_file(self, filename):
        pass
