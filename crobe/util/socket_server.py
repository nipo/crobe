import socket

class SocketClosed(Exception):
    pass

class SocketSession(object):
    def __init__(self, socket):
        self.sock = socket
        self.buffer = b''

    def refill(self, count = 1):
        while len(self.buffer) < count:
            self.wait_more()

    def wait_more(self):
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
            try:
                written = self.sock.send(data)
            except Exception:
                raise SocketClosed()
            data = data[written:]
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def start(self):
        try:
            while True:
                self.serve()
        except SocketClosed:
            return
        
class SocketServer(object):
    def __init__(self, port):
        self.port = port
        self.server_sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("::", port))
        self.server_sock.listen(1)

    def serve(self):
        while True:
            (clientsocket, address) = self.server_sock.accept()
            self.spawn(clientsocket).start()

    def spawn(self, socket):
        raise NotImplementedError()

