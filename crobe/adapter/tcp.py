from . import model
from ..protocol import pipe
import os
import socket
import struct

__all__ = []

class SocketClosed(Exception):
    pass

@model.HwRoot.register
class Enumerator(model.ExplicitEnumerator):
    def __init__(self):
        model.Enumerator.__init__(self, "tcp")

    def child_spawn(self, name):
        return Adapter.from_target(name)
            
class Adapter(model.Adapter):
    @classmethod
    def from_target(cls, name):
        hostname, port = name.rsplit(":", 1)
        
        return cls(name, hostname, int(port))

    supported_interfaces = ["pipe"]
    nickname = "tcp"

    def __init__(self, name, hostname, port):
        self.hostname = hostname
        self.port = port
        model.Adapter.__init__(self, "tcp:%s" % name)

    @property
    def firmware_info(self):
        return "TCP socket at %s:%d" % (self.hostname, self.port)

    def open(self, interface_name):
        if interface_name.lower() == "pipe":
            return PipeInterface(self)

class PipeInterface(pipe.BackgroundInterface):
    def __init__(self, port):
        super().__init__(port)

        ais = socket.getaddrinfo(self.port.hostname, self.port.port,
                                 0, 0, socket.IPPROTO_TCP)

        for i, (family, socktype, proto, canonname, sockaddr) in enumerate(ais):
            self.socket = socket.socket(family, socktype, proto)
            try:
                self.socket.connect(sockaddr)
            except ConnectionRefusedError:
                if i == len(ais) - 1:
                    raise
                continue
            break

    def freq_update(self, freq):
        return 100e6

    def _write(self, data, timeout = None):
        self.logger.protocol("< %s", data.hex())
        self.socket.settimeout(timeout)
        self.socket.send(data)

    def _read(self, size, timeout = None):
        self.logger.protocol("> expect %d...", size)
        self.socket.settimeout(timeout)
        data = b''
        while len(data) < size:
            chunk = self.socket.recv(size - len(data))
            self.logger.protocol("> %s", chunk.hex())
            data += chunk
        return data
