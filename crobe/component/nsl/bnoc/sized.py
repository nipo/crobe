import threading

class Sized(PortComponent):
    def __init__(self, port):
        super().__init__(port, "sized_io")
        self.lock = threading.Lock()
        self.reader = None
        self.rx_buf = b''

    def reset(self):
        self.port.write(b"\xff" * 1023 + b"\x00")
        time.sleep(.01)
        self.port.read()

        self.rx_buf = b''

    def frame_send(self, frame):
        self.port.write(struct.pack("<H", len(frame) - 1) + frame)

    def frame_recv(self):
        with self.lock:
            while True:
                data = self.port.read()
                self.rx_buf += data

                if len(self.rx_buf) < 2:
                    continue
                size = int.from_bytes(self.rx_buf[:2], "little") + 1
                if len(self.rx_buf) < size + 2:
                    continue
                frame = self.rx_buf[2:size + 2]
                self.rx_buf = self.rx_buf[size + 2:]

                return frame
