from ....model import PortComponent
from ....protocol import datagram
import threading
from dataclasses import dataclass
import time

@dataclass(unsafe_hash = True)
class Context:
    destination: int
    source: int

    def __init__(self, destination, source):
        self.destination = destination & 0xf
        self.source = source & 0xf

    def __bytes__(self):
        return bytes([self.destination | (self.source << 4)])

    @classmethod
    def from_bytes(cls, data):
        route = data[0]
        dst, src = route & 0xf, route >> 4
        return cls(dst, src)

class Router(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, port, "router")
        self.__waiting = {}

    @classmethod
    def __packetize(self, data, ctx):
        return bytes(ctx) + data

    @classmethod
    def __unpacketize(self, frame):
        route = frame[:1]
        data = frame[1:]
        return data, Context.from_bytes(route)

    def __packet_handle(self, blob):
        data, context = self.__unpacketize(blob)
        if context not in self.__waiting:
            self.__waiting[context] = [data]
        else:
            self.__waiting[context].append(data)
            
    def execute(self, operation_list, timeout = None):
        self.logger.protocol("Running %s, %s", operation_list, timeout)
        operation_list = list(operation_list)
        recv_pending = []

        while operation_list:
            pending = []
            for op in operation_list:
                if isinstance(op, datagram.Send):
                    assert isinstance(op.context, Context), op.context
                    blob = self.__packetize(op.data, op.context)
                    w = self.port.cmd_send(blob)
                    pending.append(w)
                elif isinstance(op, datagram.Receive):
                    r = self.port.cmd_receive()
                    pending.append(r)
                else:
                    self.logger.warning("Ingoring operation %s", op)

            self.port.execute(pending, timeout = timeout)

            for p in pending:
                if isinstance(p, datagram.Receive):
                    self.__packet_handle(p.data)

            still_to_do = []
            for op in operation_list:
                if isinstance(op, datagram.Receive):
                    rl = self.__waiting.get(op.context, [])
                    if rl:
                        r = rl.pop(0)
                        op.receive_done(r)
                    else:
                        still_to_do.append(op)
            operation_list = still_to_do

    def route(self, local_id, remote_id):
        return Route(self, local_id, remote_id)
                    
class Route(datagram.Interface):
    def __init__(self, port, local_id, remote_id):
        super().__init__(port, name = "%d>%d" % (local_id, remote_id))
        self.local_id = local_id
        self.remote_id = remote_id
        self.outbound_context = Context(destination = remote_id,
                                        source = local_id)
        self.inbound_context = Context(source = remote_id,
                                       destination = local_id)

    def cmd_send(self, data, context = None):
        return datagram.Send(data, context = context or self.outbound_context)

    def cmd_receive(self, context = None):
        return datagram.Receive(context = context or self.inbound_context)

    def execute(self, operation_list, timeout = None):
        self.logger.protocol("Running %s, %s", operation_list, timeout)
        self.port.execute(operation_list, timeout = timeout)

    def framed_endpoint(self):
        return FramedEndpoint(self)

class EndpointSend(datagram.Send):
    tag = 0

    def __init__(self, data, context = None):
        self.__class__.tag += 1
        super().__init__(bytes([self.__class__.tag & 0xff]) + data, context)

class EndpointReceive(datagram.Receive):
    def receive_done(self, data, context = None):
        super().receive_done(data[1:], context)
    
class FramedEndpoint(datagram.Interface):
    def __init__(self, port):
        super().__init__(port, "fep")

    def cmd_send(self, data, context = None):
        return EndpointSend(data, context = context or self.port.outbound_context)

    def cmd_receive(self, context = None):
        return EndpointReceive(context = context or self.port.inbound_context)
    
    def execute(self, operation_list, timeout = None):
        self.logger.protocol("Running %s, %s", operation_list, timeout)
        self.port.execute(operation_list, timeout = timeout)
