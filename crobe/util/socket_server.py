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
        self.logger.protocol("< %s", data.hex())
        self.socket.settimeout(timeout)
        self.socket.send(data)

    def _read(self, size, timeout = None):
        self.logger.protocol("> expect %s...", size)
        self.socket.settimeout(timeout)
        data = b''
        while size is None or len(data) < size:
            rsize = 1024
            if size:
                size - len(data)
            chunk = self.socket.recv(rsize)
            if len(chunk) == 0:
                raise SocketClosed()
            self.logger.protocol("> %s", chunk.hex())
            data += chunk
            if size is None:
                break
        return data

class SocketSession(model.Component):
    def __init__(self, socket):
        addrinfo = socket.getpeername()
        name = "%s:%d" % (addrinfo[0], addrinfo[1])
        super().__init__(name)
        self.sock = socket
        self.buffer = b''

    def refill(self, count = 1):
        while len(self.buffer) < count:
            self.wait_more()

    def wait_more(self):
        d = self.sock.recv(1024)
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
        while data:
            try:
                self.logger.protocol("< todo %s", data.hex())
                written = self.sock.send(data)
            except Exception:
                raise SocketClosed()
            if written:
                self.logger.protocol("< %s", data[:written].hex())
            data = data[written:]
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

class SessionThread(threading.Thread):
    def __init__(self, root):
        self.root = root
        super().__init__()

    def run(self):
        try:
            while True:
                self.root.serve()
        except SocketClosed:
            return
        
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

