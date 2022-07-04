import time
from collections import deque
from ....model import PortComponent

class Hdlc(PortComponent):
    ST_UNSYNC = 0
    ST_DATA = 1

    def __init__(self, port):
        super().__init__(port, "hdlc")
        import threading
        self.lock = threading.Lock()
        self.state = self.ST_UNSYNC
        self.buffer = b""
        self.rx_queue = deque()
        self.tx_queue = deque()

    def process(self):
        while True:
            if self.state == self.ST_UNSYNC:
                try:
                    i = self.buffer.index(b"\x7e")
                except:
                    self.buffer = b""
                    return
                self.buffer = self.buffer[i:].lstrip(b"\x7e")
                self.state = self.ST_DATA
                if not self.buffer:
                    return
                continue

            elif self.state == self.ST_DATA:
                try:
                    i = self.buffer.index(b"\x7e")
                except:
                    return
                pkt = self.buffer[:i]
                self.buffer = self.buffer[i:]
                self.state = self.ST_UNSYNC

                if not pkt:
                    continue
                frame = self.unescape(pkt)
                c = self.crc(frame[:-2])
                if c !=  frame[-2:]:
                    self.logger.protocol(">x Frame with bad CRC: %s had %s calculated %s",
                                         frame[:-2].hex(), frame[-2:].hex(), c.hex())
                    continue
                addr = frame[0]
                cmd = frame[1]
                data = frame[2:-2]

                self._frame_recv(data, addr, cmd)

    @classmethod
    def crc(self, data, init = 0):
        import crcmod
        c = crcmod.Crc(0x11021, initCrc = init ^ 0xffff)
        c.update(data)
        return (0xffff ^ int.from_bytes(c.digest(), "big")).to_bytes(2, "little")

    @classmethod
    def escape(self, data):
        r = []
        for i in data:
            if i in [0x7d, 0x7e, 0x11, 0x13, 0x91, 0x93, 0x03]:
                r.append(0x7d)
                r.append(i ^ 0x20)
            else:
                r.append(i)
        return bytes(r)

    @classmethod
    def unescape(self, data):
        r = []
        escaped = False
        for i in data:
            if escaped:
                escaped = False
                r.append(i ^ 0x20)
            elif i == 0x7d:
                escaped = True
            else:
                r.append(i)
        return bytes(r)

    def _frame_recv(self, data, addr, cmd):
        self.logger.protocol("> addr %02x cmd %02x %s",
                             addr, cmd, data.hex())
        self.rx_queue.append(data)
        
    def _frame_send(self, data, addr = 0, cmd = 0, background = False):
        self.logger.protocol("< addr %02x cmd %02x %s",
                             addr, cmd, data.hex())
        header = bytes([addr, cmd])
        crc = self.crc(header + data)
        frame = b'\x7e' + self.escape(header + data + crc) + b'\x7e'
        self.tx_queue.append(frame)
        if not background:
            self.port.tx_queue_flush()

    def tx_queue_flush(self):
        data = b''.join(self.tx_queue)
        self.tx_queue = deque()
        self.port.write(data)
            
    def frame_send(self, frame):
        self._frame_send(frame)

    def frame_recv(self):
        with self.lock:
            while True:
                try:
                    return self.rx_queue.popleft()
                except IndexError:
                    pass
                if self.tx_queue:
                    wdata = b''.join(self.tx_queue)
                    self.tx_queue = deque()
                    data = self.port.write_read(wdata, rsize = None)
                else:
                    data = self.port.read(size = None)
                if data:
                    self.buffer += data
                    self.process()

    def route(self, remote_id):
        return Route(self, remote_id)

class Route(PortComponent):
    def __init__(self, port, remote_id):
        super().__init__(port, f">{remote_id}")
        self.remote_id = remote_id
        self.waiting = []
        port.child_add(self)

    def flush(self):
        self.waiting = []
        
    def send(self, data, background = False):
        self.logger.protocol("< %s", data.hex())
        self.port._frame_send(data, addr = self.remote_id, background = background)

    def recv(self, timeout = None):
        return self.port.frame_recv()

    def execute(self, cmd, rsp_size, timeout = None):
        self.send(cmd, background = bool(rsp_size))

        if rsp_size == 0:
            return

        return self.recv()
