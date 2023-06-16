from ..protocol import pipe
import select
import threading
import sys
import tty
import time

class PipeToFd(threading.Thread):
    def __init__(self, pipe, fd):
        self.pipe = pipe
        self.fd = fd
        super().__init__()
        self.running = False

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            data = self.pipe.read(1024, timeout = .1)
            if not data:
                time.sleep(.1)
            self.fd.write(data)
            self.fd.flush()

class FdToPipe(threading.Thread):
    def __init__(self, fd, pipe):
        self.fd = fd
        self.pipe = pipe
        super().__init__()
        self.running = False

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False

    def run(self):
#        tty.setraw(self.fd)
        try:
            while self.running:
                r, w, x = select.select([self.fd], [], [], .1)
                if not r:
                    continue
                data = self.fd.read(1024)
                self.pipe.write(data)
        finally:
            tty.setcbreak(self.fd)

class PipeConsole(object):
    def __init__(self, pipe):
        self.p2f = PipeToFd(pipe, sys.stdout.buffer.raw)
        self.f2p = FdToPipe(sys.stdin.buffer.raw, pipe)

    def start(self):
        self.p2f.start()
        self.f2p.start()

    def stop(self):
        self.p2f.stop()
        self.f2p.stop()
            
