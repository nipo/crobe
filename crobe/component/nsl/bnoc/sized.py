import time
from collections import deque
from ....model import PortComponent
from ....protocol import pipe, datagram

class Sized(datagram.Interface):
    def __init__(self, port):
        assert isinstance(port, pipe.Interface)
        super().__init__(port, "sized")
        self.__buffer = b""
        self.__rx_queue = deque()

    def __process(self):
        while True:
            if len(self.__buffer) < 2:
                return
            size = int.from_bytes(self.__buffer[:2], "little") + 1
            if len(self.__buffer) < size + 2:
                return

            frame = self.__buffer[2:2+size]
            self.__buffer = self.__buffer[2+size:]
            self.__rx_queue.append(frame)

    def reset(self):
        reset = self.cmd_send(b"\xff" * 1023 + b"\x00")
        rx = self.cmd_receive(None)
        self.port.execute([reset, rx], timeout = .1)
        self.__buffer = b''
        self.__rx_queue = deque()

    @classmethod
    def __packetize(cls, data):
        assert data
        size = len(data) - 1
        return size.to_bytes(2, "little") + data
        
    def execute(self, operation_list, timeout = None):
        operation_list = list(operation_list)

        while operation_list:
            pending = []
            for op in operation_list:
                if isinstance(op, datagram.Send):
                    w = self.port.cmd_write(self.__packetize(op.data))
                    pending.append(w)
                elif isinstance(op, datagram.Receive):
                    r = self.port.cmd_read(size = None)
                    pending.append(r)
                else:
                    self.logger.warning("Ingoring operation %s", op)

            self.port.execute(pending)

            for p in pending:
                if isinstance(p, pipe.Read):
                    self.__buffer += p.data

            self.__process()

            still_to_do = []
            for op in operation_list:
                if isinstance(op, datagram.Receive):
                    if self.__rx_queue:
                        data = self.__rx_queue.popleft()
                        op.receive_done(data)
                    else:
                        still_to_do.append(op)
            operation_list = still_to_do

