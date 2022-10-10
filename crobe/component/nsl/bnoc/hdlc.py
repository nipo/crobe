from ....protocol import datagram, pipe
from ....util.timeout import TimeoutError
from collections import deque
from dataclasses import dataclass

@dataclass(unsafe_hash = True)
class Context:
    address: int
    command: int

    def __init__(self, address, command):
        self.address = address
        self.command = command

class Hdlc(datagram.Interface):
    ST_UNSYNC = 0
    ST_DATA = 1

    def __init__(self, port):
        assert isinstance(port, pipe.Interface)
        super().__init__(port, "hdlc")
        self.__state = self.ST_UNSYNC
        self.__buffer = b""
        self.__rx_queue = {}

    def __process(self):
        while True:
            if self.__state == self.ST_UNSYNC:
                try:
                    i = self.__buffer.index(b"\x7e")
                except:
                    self.__buffer = b""
                    return
                self.__buffer = self.__buffer[i:].lstrip(b"\x7e")
                self.__state = self.ST_DATA
                if not self.__buffer:
                    return
                continue

            if self.__state == self.ST_DATA:
                try:
                    i = self.__buffer.index(b"\x7e")
                except:
                    return
                pkt = self.__buffer[:i]
                self.__buffer = self.__buffer[i:]
                self.__state = self.ST_UNSYNC

                if not pkt:
                    continue
                frame = self.__unescape(pkt)
                c = self.__crc(frame[:-2])
                if c !=  frame[-2:]:
                    self.logger.protocol(">x Frame with bad CRC: %s had %s calculated %s",
                                         frame[:-2].hex(), frame[-2:].hex(), c.hex())
                    continue
                addr = frame[0]
                cmd = frame[1]
                data = frame[2:-2]

                if addr not in self.__rx_queue:
                    self.__rx_queue[addr] = deque()
                self.__rx_queue[addr].append((data, cmd))
                continue

    @classmethod
    def __crc(cls, data, init = 0):
        import crcmod
        c = crcmod.Crc(0x11021, initCrc = init ^ 0xffff)
        c.update(data)
        return (0xffff ^ int.from_bytes(c.digest(), "big")).to_bytes(2, "little")

    @classmethod
    def __escape(cls, data):
        r = []
        for i in data:
            if i in [0x7d, 0x7e, 0x11, 0x13, 0x91, 0x93, 0x03]:
                r.append(0x7d)
                r.append(i ^ 0x20)
            else:
                r.append(i)
        return bytes(r)

    @classmethod
    def __unescape(cls, data):
        r = []
        escaped = False
        for i in data:
            if escaped:
                escaped = False
                r.append(i ^ 0x20)
            elif i == 0x7d:
                escaped = True
            else:
                r.append(i)
        return bytes(r)

    @classmethod
    def packetize(cls, data, addr, cmd):
        header = bytes([addr, cmd])
        crc = cls.__crc(header + data)
        return b'\x7e' + cls.__escape(header + data + crc) + b'\x7e'
            
    def execute(self, operation_list, timeout = None):
        self.logger.protocol("Running %s, %s", operation_list, timeout)
        operation_list = list(operation_list)
        no_change = 3

        while operation_list and no_change:
            pending = []
            for op in operation_list:
                if isinstance(op, datagram.Send):
                    addr, cmd = 0, 0
                    if op.context:
                        addr, cmd = op.context.address, op.context.command
                    w = self.port.cmd_write(self.packetize(op.data, addr, cmd))
                    pending.append(w)
                elif isinstance(op, datagram.Receive):
                    r = self.port.cmd_read(size = None)
                    pending.append(r)
                else:
                    self.logger.warning("Ingoring operation %s", op)

            self.port.execute(pending, timeout = timeout and (timeout / 3))

            for p in pending:
                if isinstance(p, pipe.Read):
                    self.__buffer += p.data

            self.__process()

            still_to_do = []
            for op in operation_list:
                if isinstance(op, datagram.Receive):
                    ctx = op.context
                    q = self.__rx_queue.get(ctx.address, [])
                    if q:
                        data, cmd = q.popleft()
                        op.receive_done(data, Context(ctx.address, cmd))
                        no_change = 3
                    else:
                        still_to_do.append(op)
            no_change -= 1
            operation_list = still_to_do
        if operation_list:
            raise TimeoutError()

    def route(self, remote_id):
        return Route(self, remote_id)

class Route(datagram.Interface):
    def __init__(self, port, remote_id):
        super().__init__(port, f">{remote_id}")
        self.remote_id = remote_id
        port.child_add(self)

    def execute(self, operation_list, timeout = None):
        self.logger.protocol("Running %s, %s", operation_list, timeout)
        for op in operation_list:
            if isinstance(op, datagram.Operation):
                op.context = Context(self.remote_id, 0)
        self.port.execute(operation_list, timeout = timeout)
