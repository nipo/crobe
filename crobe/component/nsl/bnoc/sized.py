import time
from ....model import PortComponent

class Sized(PortComponent):
    def __init__(self, port):
        super().__init__(port, "sized_io")
        import threading
        self.lock = threading.Lock()
        self.rx_buf = b''

    def reset(self):
        self.port.write(b"\xff" * 1023 + b"\x00")
        time.sleep(.01)
        self.port._read()

        self.rx_buf = b''

    def frame_send(self, frame):
        assert len(frame) < 0xffff
        self.port.write((len(frame) - 1).to_bytes(2, "little") + frame)

    def frame_recv(self):
        with self.lock:
            while True:
                data = self.port._read()
                self.rx_buf += data

                if len(self.rx_buf) < 2:
                    continue
                size = int.from_bytes(self.rx_buf[:2], "little") + 1
                if len(self.rx_buf) < size + 2:
                    continue
                frame = self.rx_buf[2:size + 2]
                self.rx_buf = self.rx_buf[size + 2:]

                return frame
