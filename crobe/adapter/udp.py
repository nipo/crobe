from . import model
from ..protocol import datagram
import os
import socket
import struct

__all__ = []

class SocketClosed(Exception):
    pass

@model.HwRoot.register
class Enumerator(model.ExplicitEnumerator):
    def __init__(self):
        model.Enumerator.__init__(self, "udp")

    def child_spawn(self, name):
        return Adapter.from_target(name)
            
class Adapter(model.Adapter):
    @classmethod
    def from_target(cls, name):
        hostname, port = name.rsplit(":", 1)
        
        return cls(name, hostname, int(port))

    supported_interfaces = ["datagram"]
    nickname = "udp"

    def __init__(self, name, hostname, port):
        self.hostname = hostname
        self.port = port
        model.Adapter.__init__(self, "udp:%s" % name)

    @property
    def firmware_info(self):
        return "UDP to %s:%d" % (self.hostname, self.port)

    def open(self, interface_name):
        if interface_name.lower() == "datagram":
            return DatagramInterface(self)

class DatagramInterface(datagram.Interface):
    def __init__(self, port):
        super().__init__(port)

        ais = socket.getaddrinfo(self.port.hostname, self.port.port,
                                 0, 0, socket.IPPROTO_UDP)

        for i, (family, socktype, proto, canonname, sockaddr) in enumerate(ais):
            s = socket.socket(family, socktype, proto)
            try:
                s.connect(sockaddr)
            except ConnectionRefusedError:
                if i == len(ais) - 1:
                    raise
                continue
            self.socket = s
            self.peer_address = sockaddr
            self.socket.setblocking(False)
            break

    def execute(self, operation_list, timeout = 1.):
        self.socket.settimeout(timeout)

        for op in operation_list:
            if isinstance(op, datagram.Send):
                self.socket.send(op.data)
            elif isinstance(op, datagram.Receive):
                (data, addr) = self.socket.recvfrom(1500)
                op.data = data
                op.rcontext = addr
            else:
                self.logger.warning("Ignored unknown op %s", op)

