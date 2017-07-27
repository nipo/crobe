from .. import model
from collections import deque, defaultdict
from ..ftdi import basic
from . import base
from ...util.pretty import sci
from ...model import PortComponent
from ...component.arm import dp
from ..protocol import base as pbase
from ..protocol import swd
import threading
import struct
import time

class MsgMux(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, "mux", port)
        self.rx_queue_cond = threading.Condition(threading.Lock())
        self.rx_buf = bytearray()
        self.dest = {}
        self.reader = None

    def register(self, id, target):
        self.dest[id] = target
        
    def reset(self):
        self.port.write(b"\xff" * 1023 + b"\x00")
        self.port.rx_flush()
        self.rx_buf = bytearray()
        time.sleep(.01)
        
    def put(self, dst, src, tag, data):
        assert len(data) < (1 << 16) - 2
        route = dst | (src << 4)
        self.port.write(struct.pack("<HBB", len(data) + 1, route, tag) + data)

    def read(self, size):
        while len(self.rx_buf) < size:
            self.rx_buf += self.port.read(size - len(self.rx_buf))
            
        r = self.rx_buf[:size]
        self.rx_buf = self.rx_buf[size:]
        return r

    def wait(self):
        with self.rx_queue_cond:
            if self.reader:
                self.rx_queue_cond.wait()
                return

            self.reader = self
            try:
                length, route, tag = struct.unpack("<HBB", self.read(4))
                data = self.read(length - 1)
                dst = route & 0xf
                src = route >> 4
                if dst not in self.dest:
                    self.logger.warning("Dropping message for %d", dst)
                else:
                    self.dest[dst].handle(src, tag, data)
            except:
                raise
            finally:
                self.reader = None

class RoutedPath(PortComponent):
    def __init__(self, port, local_id):
        PortComponent.__init__(self, "%d<" % local_id, port)
        self.local_id = local_id
        port.register(local_id, self)
        self.last_tag = 0
        self.rx_q = {}
        self.rx_q_cond = threading.Condition()

    def put(self, peer, tag, blob):
        self.port.put(peer, self.local_id, tag, blob)

    def handle(self, peer, tag, data):
        with self.rx_q_cond:
            self.rx_q[(peer, tag)] = data
            self.rx_q_cond.notify_all()
        
    def get(self, peer, tag):
        with self.rx_q_cond:
            while True:
                try:
                    return self.rx_q.pop((peer, tag))
                except KeyError:
                    self.port.wait()
        
    def execute(self, peer, blob, rsp_size, tag = None):
        if tag is None:
            tag = (self.last_tag + 1) & 0xff
            self.last_tag = tag
        self.put(peer, tag, blob)
        return self.get(peer, tag)
        
class Interface(swd.Interface):
    CMD_TURNAROUND   = 0xd0
    CMD_RUN          = 0x00
    CMD_ABORT        = 0xc0
    CMD_BITBANG      = 0xe0
    CMD_READ         = 0x90
    CMD_WRITE        = 0x80

    RSP_OP_MASK          = 0xf0
    RSP_ACK_MASK         = 0x07
    RSP_PAR_ERROR        = 0x08

    BASE_FREQ = 60e6

    SWD_PORT_CID = 0
    CONFIG_CID = 1
    CONFIG_REG_FREQ = 0
    CONFIG_REG_SRST = 1
    CONFIG_REG_TRST = 2
    
    def __init__(self, adapter, mux):
        self.__turnaround_cycles = 1
        self.__turnaround_dirty = True
        swd.Interface.__init__(self, adapter)
        self.mux = RoutedPath(mux, 0xf)
        self.__reset = False
        self.__divisor = int(self.BASE_FREQ / 1e6 - 1)
        self.__divisor_dirty = True

    @property
    def reset(self):
        return self.__reset

    @reset.setter
    def reset(self, value):
        if self.__reset == bool(value):
            return

        self.logger.info("%s reset pin", "holding" if value else "releasing")
        self.__reset = bool(value)
        self.mux.execute(self.CONFIG_CID, struct.pack("<BL", self.CONFIG_REG_SRST, int(self.__reset)), 1)
        
    @property
    def freq(self):
        return self.BASE_FREQ / self.__divisor / 2

    @freq.setter
    def freq(self, value):
        self.__divisor = min((1<<16, max((1, int(self.BASE_FREQ / float(value) / 2)))))
        self.__divisor_dirty = True
        
    @property
    def turnaround_cycles(self):
        return self.__turnaround_cycles

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        self.logger.debug("Changing turnaround_cycles from %d to %d", self.__turnaround_cycles, cycles)
        if cycles != self.__turnaround_cycles:
            self.__turnaround_dirty = True
            self.__turnaround_cycles = cycles

    def _execute(self, operation_list):
        ops = deque(operation_list)
        max_size = 512
        
        while ops:
            cmd = bytearray([0] * max_size)
            cmd_size = 0
            rsp_size = 0

            pending = deque()

            while ops and cmd_size < max_size - 16 and rsp_size < max_size - 16:
                op = ops.popleft()
                pending.append(op)

                if self.__turnaround_dirty:
                    self.logger.debug("Turnaround dirty, now %d", self.__turnaround_cycles)
                    cmd[cmd_size] = self.CMD_TURNAROUND | (self.__turnaround_cycles - 1)
                    cmd_size += 1
                    rsp_size += 1
                    self.__turnaround_dirty = False

                if self.__divisor_dirty:
                    d = self.__divisor
                    self.mux.execute(self.CONFIG_CID, struct.pack("<BL", self.CONFIG_REG_FREQ, d - 1), 1)
                    self.__divisor_dirty = False

                if isinstance(op, swd.Read):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))
                    cmd[cmd_size] = self.CMD_READ | (ap << 5) | addr
                    op.__offset = rsp_size
                    cmd_size += 1
                    rsp_size += 5

                    if ap:
                        cmd[cmd_size] = self.CMD_RUN | 10
                        cmd_size += 1
                        rsp_size += 1
                    
                elif isinstance(op, swd.Write):
                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))

                    cmd[cmd_size] = self.CMD_WRITE | (ap << 5) | addr
                    cmd[cmd_size + 1 : cmd_size + 5] = struct.pack("<L", op.data)
                    op.__offset = rsp_size
                    cmd_size += 5
                    rsp_size += 1

                    if ap:
                        cmd[cmd_size] = self.CMD_RUN | 10
                        cmd_size += 1
                        rsp_size += 1
                    
                elif isinstance(op, swd.Wakeup):
                    self.turnaround_cycles = 1
                    cmd[cmd_size] = self.CMD_RUN | 0x40 | 49
                    cmd_size += 1
                    rsp_size += 1

                elif isinstance(op, swd.Run):
                    count = op.cycles
                    while count:
                        c = min((64, count))
                        count -= c
                        cmd[cmd_size] = self.CMD_RUN | (c - 1)
                        cmd_size += 1
                        rsp_size += 1

                elif isinstance(op, swd.JtagToSwd):
                    cmd[cmd_size : cmd_size + 5] = [self.CMD_BITBANG | 15, 0x9e, 0xe7, 0, 0]
                    cmd_size += 5
                    rsp_size += 1

                else:
                    raise base.ProtocolError("Unknown SWD operation %s" % type(op))

            in_blob = self.mux.execute(self.SWD_PORT_CID, cmd[:cmd_size], rsp_size)

            for idx, op in enumerate(pending):
                if isinstance(op, (swd.Read, swd.Write)):
                    rsp = in_blob[op.__offset]
                    
                    try:
                        ack = swd.Ack(0x7 & rsp)
                    except ValueError:
                        ack = swd.Ack.INVALID

                    if rsp & self.RSP_PAR_ERROR:
                        ack = swd.Ack.INVALID

                    op.ack = ack

                    if isinstance(op, swd.Read):
                        op.data, = struct.unpack("<L", in_blob[op.__offset + 1 : op.__offset + 5])

class Adapter(basic.Adapter, base.Reflasher):
    supported_interfaces = ["swd"]
    firmware_info = "SWD offload mux"

    def open(self, interface_name):
        assert interface_name == "swd"

        self.reprogram("swd_dp")

        fifo = self.device.open(interface = "A", mode = "ft245_sync_fifo")

        mux = MsgMux(fifo)
        mux.reset()
        
        return Interface(self, mux)

@model.Enumerator.register
class Enumerator(base.Enumerator):
    adapter_class = Adapter

    def __init__(self):
        base.Enumerator.__init__(self, "Proby, offloaded", "oproby")
