import socket
import logging
import struct
from ..bitstring import BitString
from ..util.socket_server import *
from ..util.pretty import metric

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
                    self.pending.append(self.interface.cmd_tap_reset())
                    
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
            tdo += BitString(0, off - len(tdo))
            tdo += op.tdo
        tdo += BitString(0, len(tdi) - len(tdo))

        self.pending = []

        return tdo

class XvcdSession(SocketSession):
    def __init__(self, socket, interface):
        SocketSession.__init__(self, socket)
        self.jtag = JtagHandler(interface)

    def serve(self):
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
        self.jtag.interface.freq = 1 / period
        logging.info("Setting freq to %s, had %s", metric(1/period, "Hz"), metric(self.jtag.interface.freq, "Hz"))
        self.write(struct.pack("<L", int(1e9 / self.jtag.interface.freq)))

class XvcdServer(SocketServer):
    def __init__(self, port, interface):
        SocketServer.__init__(self, port)
        self.interface = interface

    def spawn(self, socket):
        return XvcdSession(socket, self.interface)

def main():
    from . import base
    from ..adapter.protocol.jtag import Interface

    class Tool(base.Root):
        def c32_port_declare(self):
            self.parser.add_argument('--port', '-p', type = int, default = 2542,
                                         help = "TCP port to listen on")

        def c32_port_parse(self, args):
            self.port = args.port

    args = Tool("XVCD Server")

    intf = args.roots[0]

    if not isinstance(intf, Interface):
        raise ValueError("Expected a JTAG interface. Try -e [adapter]/jtag.")
    
    print("Adapter:", intf.port.firmware_info)
    print("Serial:", intf.port.serial_number)
    print("Freq:", metric(intf.freq, "Hz"))

    try:
        intf.reset = False
    except NotImplementedError:
        pass
    XvcdServer(args.port, intf).serve()

    
if __name__ == '__main__':
    main()


