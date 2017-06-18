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
                   STATE_PAUSE, STATE_EXIT1, STATE_UPDATE, STATE_EXIT2,
                   STATE_UPDATE, STATE_SELECT_DR]]

    def __init__(self, interface):
        self.interface = interface
        self.state = self.STATE_RESET

    def reset(self):
        logging.info("TAP Reset")
        self.interface.tap_reset()

    def shift(self, tdi):
        logging.info("TAP Shift TDI:%s", tdi)
        tdo = self.interface.shift(tdi)
        logging.info(" -> TDO:%s", tdo)
        return tdo or BitString()

    def run(self, count):
        logging.info("TAP run, %d cycles", count)
        return self.interface.run(count)

    def capture_dr(self):
        logging.info("TAP Capture DR")
        return self.interface.capture_dr()

    def capture_ir(self):
        logging.info("TAP Capture IR")
        return self.interface.capture_ir()

    def handle(self, tms, tdi):
        tdo = BitString()

        last_new_state = 0
        last_shift = 0
        point = 0
        while point < len(tms):
            next_state = self.NEXT_STATE[int(tms[point])][self.state]
            if self.state != next_state:
                logging.debug("State change %s -> %s", self.STATE_NAME[self.state], self.STATE_NAME[next_state])
                if next_state == self.STATE_CAPTURE:
                    if self.state == self.STATE_SELECT_IR:
                        self.capture_ir()
                    else:
                        self.capture_dr()

                if self.state == self.STATE_SHIFT:
                    data = tdi[last_new_state : point + 1]
                    tdo += tdi[last_shift : last_new_state] + self.shift(data)
                    last_shift = point + 1
                elif self.state == self.STATE_RTI:
                    self.run(point + 1 - last_new_state)
                elif self.state == self.STATE_RESET:
                    self.reset()
                    
                self.state = next_state
                last_new_state = point + 1
            point += 1

        if self.state == self.STATE_SHIFT and last_new_state != len(tdi):
            tdo += tdi[last_shift : last_new_state] + self.shift(tdi[last_new_state : len(tms)])
        else:
            tdo += tdi[last_shift : len(tms)]

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

    def serve(self):
        try:
            while True:
                self.refill(6)

                if self.buffer.startswith(b"shift:"):
                    self.read(6)
                    self.handle_shift()
                else:
                    raise ValueError("Unknown command: %r" % (self.buffer.split(b':')[0]))
        except SocketClosed:
            pass

    def handle_shift(self):
        bits, = struct.unpack("<L", self.read(4))
        bytes = (bits + 7) // 8
        tms = BitString(self.read(bytes), bits)
        tdi = BitString(self.read(bytes), bits)
        logging.info("Ready to shift command TMS:%s TDI:%s", tms, tdi)
        tdo = self.jtag.handle(tms, tdi)
        logging.info("Had TDO:%s", tdo)

        assert len(tdo) == bits
        
        self.write(tdo.data)

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


