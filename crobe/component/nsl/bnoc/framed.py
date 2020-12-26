import time
from ....model import PortComponent

class Framed(PortComponent):
    def __init__(self, port):
        super().__init__(port, "framed_io")
        self.rx_buf = []

    def reset(self):
        while self.port.read():
            continue
        self.rx_buf = []

    def frame_send(self, frame):
        self.logger.debug("< %s", frame.hex())
        enc = list(frame)
        enc[-1] |= 0x100
        self.port.write(enc)

    def frame_recv(self):
        retries = 3
        while True:
            more_data = self.port.read()

            self.logger.debug("read %d %s", retries, more_data)

            self.rx_buf += more_data

            for i, word in enumerate(self.rx_buf):
                if word & 0x100:
                    frame = bytes([x & 0xff for x in self.rx_buf[:i+1]])
                    self.rx_buf = self.rx_buf[i+1:]
                    self.logger.debug("> %s", frame.hex())
                    self.logger.debug("pending %s", ' '.join(hex(x) for x in self.rx_buf))
                    return frame

            if more_data:
                retries = 3
                continue

            time.sleep(.05)

            retries -= 1
            if retries <= 0:
                return None

    def execute(self, cmd, rsp_size = None):
        self.frame_send(cmd)
        if rsp_size == 0:
            return
        return self.frame_recv()
