from ..protocol import datagram, pipe
from ..util.timeout import TimeoutError
from collections import deque
from dataclasses import dataclass
import time
from ..util.crc import Crc
alg = Crc.from_name("hdlc")

@dataclass(unsafe_hash = True)
class Context:
    address: int
    command: int

    def __init__(self, address, command):
        self.address = address
        self.command = command

@pipe.Interface.db.register("hdlc")
class Hdlc(datagram.Interface):
    ST_UNSYNC = 0
    ST_DATA = 1

    def __init__(self, port):
        assert isinstance(port, pipe.Interface)
        super().__init__(port, "hdlc")
        self.__state = self.ST_UNSYNC
        self.__buffer = b""
        self.__pending = []

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
                self.logger.protocol("> ? %s", frame.hex())
                c = self.__crc(frame[:-2])
                if c !=  frame[-2:]:
                    self.logger.protocol(">x Frame with bad CRC: %s had %s calculated %s",
                                         frame[:-2].hex(), frame[-2:].hex(), c.hex())
                    continue

                self.logger.protocol(">x OK %s", frame[:-2].hex())
                self.__pending.append(frame[:-2])
                continue

    @classmethod
    def __crc(cls, data, init = 0):
        state = alg(init)
        state.update(data)
        return bytes(state)

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
    def packetize(cls, data):
        crc = cls.__crc(data)
        return b'\x7e' + cls.__escape(data + crc) + b'\x7e'
            
    def execute(self, operation_list, timeout = None):
        operation_list = list(operation_list)
        no_change = 3
        deadline = time.time() + (timeout or 0)
        first = True
        
        while operation_list:
            self.logger.protocol("At begin of iteration %s %s", operation_list, timeout)
            pending = []
            has_rx = False
            for op in operation_list:
                if isinstance(op, datagram.Send):
                    if op.context:
                        header = bytes([op.context.address, op.context.command])
                        w = self.port.cmd_write(self.packetize(header + op.data))
                    else:
                        w = self.port.cmd_write(self.packetize(op.data))
                    pending.append(w)
                elif isinstance(op, datagram.Receive):
                    has_rx = True
                else:
                    self.logger.warning("Ingoring operation %s", op)

            if has_rx:
                r = self.port.cmd_read(size = None)
                pending.append(r)

            timeout = deadline - time.time()
            if timeout < .01:
                timeout = .01
            if first:
                timeout = None
            first = False
                
            try:
                self.port.execute(pending, timeout = timeout)
            except TimeoutError:
                if time.time() > deadline:
                    raise

            for p in pending:
                if isinstance(p, pipe.Read):
                    self.__buffer += p.data

            self.__process()

            still_to_do = []
            for op in operation_list:
                if not isinstance(op, datagram.Receive):
                    continue

                self.logger.protocol("collect %s %s %s", self.__buffer.hex(), self.__pending, op)
                selected = None
                context = None
                for index, data in enumerate(self.__pending):
                    if not op.context:
                        selected = index
                        context = None
                    elif op.context.address == data[0]:
                        selected = index
                        context = Context(data[0], data[1])
                        data = data[2:]
                    else:
                        continue

                    op.receive_done(data, context = context)
                    self.logger.protocol("popped %s %s", data.hex(), context)
                    self.__pending.pop(selected)
                    break

                if selected is None:
                    still_to_do.append(op)

            self.logger.protocol("At end of iteration still %s", still_to_do)
            operation_list = still_to_do

        if operation_list:
            raise TimeoutError(operation_list)

    def child_spawn(self, crit):
        from ..db import NoMatch
        from ..model import BadInvocation
        print(crit)
        if not crit.startswith("addr"):
            raise NoMatch()
        try:
            addr = int(crit[4:], 16)
        except:
            raise BadInvocation(crit)
        return HdlcCircuit(self, addr)
        
class HdlcCircuit(datagram.Interface):
    def __init__(self, port, addr):
        assert isinstance(port, datagram.Interface)
        super().__init__(port, f"addr{addr:02x}")
        self.addr = addr
            
    def execute(self, operation_list, timeout = None):
        for op in operation_list:
            if op.context:
                op.context.address = self.addr
            else:
                op.context = Context(address = self.addr, command = 0)

        self.port.execute(operation_list, timeout = timeout)
