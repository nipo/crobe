import socket
import logging
import struct
from ..bitstring import BitString

class JtagHandler(object):
    STATE_RESET = 0
    STATE_RTI = 1
    STATE_SELECT_DR = 2
    STATE_SELECT_IR = 3
    STATE_CAPTURE = 4
    STATE_SHIFT = 5
    STATE_EXIT1 = 6
    STATE_PAUSE = 7
    STATE_EXIT2 = 8
    STATE_UPDATE = 9

    STATE_NAME = [
        "Reset",
        "Rti",
        "Select DR",
        "Select IR",
        "Capture",
        "Shift",
        "Exit1",
        "Pause",
        "Exit2",
        "Update",
        ]

    NEXT_STATE = [[STATE_RTI, STATE_RTI, STATE_CAPTURE, STATE_CAPTURE,
                   STATE_SHIFT, STATE_SHIFT, STATE_PAUSE, STATE_PAUSE,
                   STATE_SHIFT, STATE_RTI],
                  [STATE_RESET, STATE_SELECT_DR, STATE_SELECT_IR, STATE_RESET,
                   STATE_EXIT1, STATE_EXIT1, STATE_UPDATE, STATE_EXIT2,
                   STATE_UPDATE, STATE_SELECT_DR]]

    def __init__(self, interface):
        self.interface = interface
        self.state = self.STATE_RESET
        self.ir = False
        self.pending = []

    def handle(self, tms, tdi):
        #if (self.ir and self.state == self.STATE_EXIT1 and int(tms) == 0x17 and len(tms) == 5) \
        #       or (not self.ir and self.state == self.STATE_EXIT1 and int(tms) == 0xb and len(tms) == 4):
        #    logging.warning("Workaround bug like anyone else, but dont know why...")
        #    return tdi

        last_new_state = 0
        last_shift = 0
        tdo_parts = []

        for point in range(len(tms)):
            next_state = self.NEXT_STATE[int(tms[point])][self.state]
            if self.state != next_state:
                if next_state == self.STATE_CAPTURE:
                    if self.state == self.STATE_SELECT_IR:
                        self.ir = True
                        self.pending.append(self.interface.cmd_capture_ir())
                    else:
                        self.ir = False
                        self.pending.append(self.interface.cmd_capture_dr())

                if self.state == self.STATE_SHIFT:
                    op = self.interface.cmd_shift(tdi[last_new_state : point + 1])
                    self.pending.append(op)
                    tdo_parts.append((op, last_new_state))
                    last_shift = point + 1

                elif self.state == self.STATE_RTI:
                    self.pending.append(self.interface.cmd_run(point + 1 - last_new_state))

                elif self.state == self.STATE_RESET:
                    self.pending = [self.interface.cmd_tap_reset()]
                    
                self.state = next_state
                last_new_state = point + 1

        if self.state == self.STATE_SHIFT and last_new_state != len(tdi):
            op = self.interface.cmd_shift(tdi[last_new_state : len(tms)])
            self.pending.append(op)
            tdo_parts.append((op, last_new_state))

        elif self.state == self.STATE_RTI and last_new_state != len(tdi):
            self.pending.append(self.interface.cmd_run(len(tms) - last_new_state))

        if not tdo_parts:
            return tdi

        logging.info("Running %s", self.pending)
        self.interface.execute(self.pending)

        tdo = BitString()
        for op, off in tdo_parts:
            tdo.enlarge(off)
            tdo += op.tdo
        tdo.enlarge(len(tdi))

        self.pending = []

        return tdo


class SocketClosed(Exception):
    pass

class XvcdSession(object):
    def __init__(self, socket, interface):
        self.sock = socket
        self.jtag = JtagHandler(interface)
        self.buffer = b''

    def refill(self, count = 1):
        while len(self.buffer) < count:
            d = self.sock.recv(1024)
            if not d:
                raise SocketClosed()
            self.buffer += d

    def read(self, count):
        self.refill(count)
        blob = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return blob

    def write(self, data):
        while data:
            written = self.sock.send(data)
            data = data[written:]
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def serve(self):
        try:
            while True:
                self.refill(8)

                if self.buffer.startswith(b"shift:"):
                    self.read(6)
                    self.handle_shift()
                elif self.buffer.startswith(b"getinfo:"):
                    self.Read(8)
                    self.handle_getinfo()
                elif self.buffer.startswith(b"settck:"):
                    self.read(7)
                    self.handle_settck()
                else:
                    raise ValueError("Unknown command: %r" % (self.buffer.split(b':')[0]))
        except SocketClosed:
            pass

    def handle_shift(self):
        bits, = struct.unpack("<L", self.read(4))
        bytes = (bits + 7) // 8
        tms = BitString(self.read(bytes), bits)
        tdi = BitString(self.read(bytes), bits)
        tdo = self.jtag.handle(tms, tdi)

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
        self.jtag.interface.speed = 1 / period
        logging.info("Setting speed to %d, had %d", int(1/period), int(self.jtag.interface.speed))
        self.write(struct.pack("<L", int(1e9 / self.jtag.interface.speed)))

class XvcdServer(object):
    def __init__(self, port, interface):
        self.interface = interface
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((socket.gethostname(), port))
        self.server_sock.listen(1)

    def serve(self):
        while True:
            (clientsocket, address) = self.server_sock.accept()
            XvcdSession(clientsocket, self.interface).serve()

def main():
    from . import base
    from ..component.fpga.spartan6 import Spartan6

    class Tool(base.Speed):
        forced_interface = "jtag"
        def c32_port_declare(self):
            self.parser.add_argument('--port', '-p', type = int, default = 2542,
                                         help = "TCP port to listen on")

        def c32_port_parse(self, args):
            self.port = args.port

    args = Tool("XVCD Server")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Speed:", args.interface.speed)

    try:
        args.interface.reset = False
    except NotImplementedError:
        pass
    XvcdServer(args.port, args.interface).serve()

    
if __name__ == '__main__':
    main()


