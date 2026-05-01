import socket
import logging
import struct
from ..bitstring import BitString
from ..jtag.walker import JtagTmsWalker
from ..util.socket_server import *
from ..util.pretty import metric

class XvcdSession(SocketSession):
    def __init__(self, socket, interface):
        SocketSession.__init__(self, socket)
        self.interface = interface
        self.jtag = JtagTmsWalker(interface)

    def serve(self):
        self.logger.info("Refill")
        self.refill(6)

        self.logger.info("buffer: %s", self.buffer)
        if self.buffer.startswith(b"shift:"):
            self.read(6)
            self.handle_shift()
        elif self.buffer.startswith(b"getinf"):
            self.read(8)
            self.handle_getinfo()
        elif self.buffer.startswith(b"settck"):
            self.read(7)
            self.handle_settck()
        else:
            raise ValueError("Unknown command: %r" % (self.buffer.split(b':')[0]))

    def handle_shift(self):
        bits, = struct.unpack("<L", self.read(4))
        bytes = (bits + 7) // 8
        tms = BitString(self.read(bytes), bits)
        tdi = BitString(self.read(bytes), bits)
        tdo = self.jtag.process(tms, tdi)

        assert len(tdo) == bits
        self.write(tdo.data)

    def handle_getinfo(self):
        logging.info("Answering to version information")
        assert not self.buffer
        self.write(b"xvcServer_v1.0:4096\n")

    def handle_settck(self):
        ns, = struct.unpack("<L", self.read(4))
        period = 1e-9 * ns
        self.buffer = b""
        freq = self.interface.freq_cap("vcd", 1 / period)
        logging.info("Setting freq to %s, had %s", metric(1/period, "Hz"), metric(freq, "Hz"))
        self.write(struct.pack("<L", int(1e9 / freq)))

class XvcdServer(SocketServer):
    def __init__(self, port, interface):
        SocketServer.__init__(self, port)
        self.interface = interface

    def spawn(self, socket):
        return XvcdSession(socket, self.interface)
