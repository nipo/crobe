from .message import *
from ..util.socket_server import SocketSession
from collections import deque

class Session(SocketSession):
    def __init__(self, socket):
        SocketSession.__init__(self, socket)
        self.rsp_queue = deque()
        self.packet_ack = True

    def serve(self):
        while self.buffer:
            if self.buffer.startswith(b'$'):
                self.serve_command()
                continue

            elif self.buffer.startswith(b'+') and self.packet_ack:
                try:
                    self.rsp_queue.popLeft()
                except:
                    pass
            
            elif self.buffer.startswith(b'-') and self.packet_ack:
                rsp = self.rsp_queue[0]

            elif self.buffer.startswith(b'\x03'):
                self.handle_interrupt()

            self.read(1)
            continue
        self.wait_more()

    def serve_command(self):
        end = self.buffer.find(b"#")
        if end < 0 or end + 2 >= len(self.buffer):
            return self.wait_more()

        packet = self.read(end + 3)
        try:
            cmd = Command.from_packet(self, packet)
        except ValueError:
            self.write(b'-')
            return self.wait_more()

        if self.packet_ack:
            self.write(b'+')
        self.handle(cmd)

    def respond(self, response):
        if self.packet_ack:
            self.rsp_queue.append(response)
        self.write(response.to_packet())
