import socket
from .. import model
from ..protocol import pipe
import threading

class SocketClosed(Exception):
    pass

class SocketPipe(pipe.BackgroundInterface):
    def __init__(self, socket):
        addrinfo = socket.getpeername()
        name = "%s:%d" % (addrinfo[0], addrinfo[1])
        super().__init__(socket, name)
        self.socket = socket

    def freq_update(self, freq):
        return 100e6

    def _write(self, data, timeout = None):
        self.logger.protocol("S< %s", data.hex())
        self.socket.settimeout(timeout)
        self.socket.send(data)
        return len(data)

    def _read(self, size, timeout = None):
        self.logger.protocol("> expect %s...", size)
        self.socket.settimeout(timeout or 5)
        data = b''
        while size is None or len(data) < size:
            if size:
                rsize = size - len(data)
            else:
                rsize = 1024
            chunk = self.socket.recv(rsize)
            if len(chunk) == 0:
                raise SocketClosed()
            self.logger.protocol("S> %s", chunk.hex())
            data += chunk
            if size is None:
                break
        return data

class SocketSession(model.Component):
    def __init__(self, socket, name = None):
        if name is None:
            try:
                addrinfo = socket.getpeername()
                name = "%s:%d" % (addrinfo[0], addrinfo[1])
            except AttributeError:
                name = "session"
        super().__init__(name)
        self.sock = socket
        self.buffer = b''

    def serve(self):
        ...

    def refill(self, count = 1):
        while len(self.buffer) < count:
            self.wait_more(count - len(self.buffer))

    def wait_more(self, count = 1024):
        d = None
        while not d:
            try:
                d = self.sock.read(count)
            except TimeoutError:
                continue
        if not d:
            raise SocketClosed()
        self.logger.protocol("> %s", d.hex())
        self.buffer += d
        
    def read(self, count):
        self.refill(count)
        blob = self.buffer[:count]
        self.buffer = self.buffer[count:]
        return blob

    def write(self, data):
        tw = 0
        while data:
            written = 0
            try:
                self.logger.protocol("< todo %s", data.hex())
                written = self.sock.write(data)
            except Exception:
                raise SocketClosed()
            if written:
                self.logger.protocol("< %s", data[:written].hex())
            tw += written or 0
            data = data[written:]
#        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return tw

class SessionThread(threading.Thread):
    def __init__(self, root):
        self.root = root
        super().__init__()

    def run(self):
        self.root.logger.info("Starting")
        try:
            while True:
                self.root.serve()
        except SocketClosed:
            pass
        self.root.logger.info("Done")
        
class SocketServer(object):
    handler_class = SocketSession

    def __init__(self, port):
        self.running_sessions = set()
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("::", port))
        self.server_sock.listen(1)

    def serve(self):
        while True:
            (clientsocket, address) = self.server_sock.accept()
            pipe = SocketPipe(clientsocket)
            pipe.start()
            s = SessionThread(self.spawn(pipe))
            self.running_sessions.add(s)
            s.start()

    def join(self):
        for s in self.running_sessions:
            s.join()

    def spawn(self, pipe):
        return self.handler_class(pipe)

