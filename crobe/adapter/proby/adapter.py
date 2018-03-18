from .. import model
from ..ftdi import basic
from ...loadable.object import Program
import logging
import os
import os.path
import time
from collections import deque, defaultdict
from ...util.pretty import metric
from ...model import PortComponent
from ...component.arm import dp
from ..protocol import base as pbase
from ..protocol import swd, i2c, chipcon
import threading
import struct

__all__ = ['Proby', 'Enumerator']

class MsgMux(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, port, "mux")
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
            except Exception:
                raise
            finally:
                self.reader = None

class RoutedPath(PortComponent):
    def __init__(self, port, local_id):
        PortComponent.__init__(self, port, "%d<" % local_id)
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

class SwdInterface(swd.Interface):
    CMD_TURNAROUND   = 0xd0
    CMD_RUN          = 0x00
    CMD_ABORT        = 0xc0
    CMD_BITBANG      = 0xe0
    CMD_READ         = 0x90
    CMD_WRITE        = 0x80

    RSP_OP_MASK          = 0xf0
    RSP_ACK_MASK         = 0x07
    RSP_PAR_ERROR        = 0x08

    SWD_PORT_CID = 0
    CONFIG_CID = 1

    STATUS_REG_BASE_FREQ = 2
    CONFIG_REG_RATE = 0
    CONFIG_REG_SRST = 1
    CONFIG_REG_TRST = 2
    
    def __init__(self, adapter, mux):
        self.__turnaround_cycles = 1
        self.__turnaround_dirty = True
        swd.Interface.__init__(self, adapter, adapter.name)
        self.mux = RoutedPath(mux, 0xf)
        self.base_freq = int.from_bytes(
            self.mux.execute(self.CONFIG_CID, struct.pack("<B", 0x80 | self.STATUS_REG_BASE_FREQ), 5)[1:],
            byteorder = 'little')

        self.logger.info("Found proby with internal clock of %s", metric(self.base_freq, "Hz"))
        
        self.__reset = False
        self.__rate = 1000
        self.__rate_dirty = True

        self.freq_cap("hardware", 75e6)

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
        return self.__rate / 2

    @freq.setter
    def freq(self, freq):
        if not freq:
            freq = 15e6
        self.__rate = min((1 << 26) - 1, max(1, int(float(freq) * 2)))
        self.__rate_dirty = True
        
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

                if self.__rate_dirty:
                    self.mux.execute(self.CONFIG_CID, struct.pack("<BL", self.CONFIG_REG_RATE, self.__rate), 1)
                    self.__rate_dirty = False

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

class I2cInterface(i2c.Interface):
    CMD_READ_ACK     = 0xc0
    CMD_READ_NACK    = 0x80
    CMD_WRITE        = 0x40
    CMD_START        = 0x20
    CMD_STOP         = 0x21
    CMD_DIV          = 0x00

    I2C_PORT_CID = 0
    CONFIG_CID = 1
    
    REG_SRST = 0
    REG_BASE_FREQ = 1

    def __init__(self, adapter, mux):
        i2c.Interface.__init__(self, adapter, adapter.name)
        self.mux = RoutedPath(mux, 0xf)
#        self.base_freq = int.from_bytes(
#            self.mux.execute(self.CONFIG_CID, struct.pack("<B", 0x80 | self.REG_BASE_FREQ), 5)[1:],
#            byteorder = 'little')

        self.base_freq = 1e6

#        self.logger.info("Found I2C proby with internal clock of %s", metric(self.base_freq, "Hz"))
        self.freq_cap("hardware", 1e6)
        self.__reset = False
        self.__div = 4

    @property
    def reset(self):
        return self.__reset

    @reset.setter
    def reset(self, value):
        if self.__reset == bool(value):
            return

        self.logger.info("%s reset pin", "holding" if value else "releasing")
        self.__reset = bool(value)
        self.mux.execute(self.CONFIG_CID, struct.pack("<BL", self.REG_SRST, int(self.__reset)), 1)
        
    @property
    def freq(self):
        return self.base_freq / self.__div / 2

    @freq.setter
    def freq(self, freq):
        if not freq:
            freq = 1e6
        self.__div = min(0x1f, max(4, int(self.base_freq / float(freq) / 2)))

    def _execute(self, operation_list):
        ops = list(operation_list)
        cmd = [self.CMD_DIV | self.__div]
        rsp_size = 1
        starts = []

        prev = None
        for i, cur in enumerate(ops):
            next = ops[i+1] if i < len(ops) - 1 else None

            if not prev or (isinstance(prev, i2c.Read) != isinstance(cur, i2c.Read)):
                cmd.append(self.CMD_START)
                rsp_size += 1
                cmd += [self.CMD_WRITE | 0, (cur.addr << 1) | int(isinstance(cur, i2c.Read))]
                starts.append(rsp_size)
                rsp_size += 1

            last = not next or (isinstance(cur, i2c.Read) != isinstance(next, i2c.Read))

            if isinstance(cur, i2c.Read):
                cur.__rsp = []
                for offset in range(0, cur.size, 0x40):
                    last_offset = cur.size - 0x40 <= offset
                    size = min(cur.size - offset, 0x40)
                    cur.__rsp.append((rsp_size, rsp_size + size))
                    rsp_size += size

                    if last and last_offset:
                        cmd.append(self.CMD_READ_NACK | (size - 1))
                    else:
                        cmd.append(self.CMD_READ_ACK | (size - 1))
        
            elif isinstance(cur, i2c.Write):
                cur.__rsp = []
                for offset in range(0, len(cur.data), 0x40):
                    size = min(len(cur.data) - offset, 0x40)
                    cur.__rsp.append((rsp_size, rsp_size + size))
                    rsp_size += size

                    cmd.append(self.CMD_WRITE | (size - 1))
                    cmd += cur.data[offset : offset + size]

            else:
                raise base.ProtocolError("Unknown I2C operation %s" % type(op))

            prev = cur

        cmd.append(self.CMD_STOP)
        rsp_size += 1

        rsp = self.mux.execute(self.I2C_PORT_CID, bytes(cmd), rsp_size)

        for op in ops:
            data = b''.join(rsp[start:end] for (start, end) in op.__rsp)
            if isinstance(op, i2c.Read):
                op.data = data
            elif not all(op.data[:-1]):
                raise i2c.DataNack()

        for s in starts:
            if not rsp[s]:
                raise i2c.AddressNack()

class CcInterface(chipcon.Interface):
    CMD_CMD          = staticmethod(lambda out_count, in_count, wait: (in_count | ((out_count - 1) << 2)) | (int(bool(wait)) << 4))
    CMD_ACQUIRE      = 0x20
    CMD_RESET        = 0x21
    CMD_WAIT         = staticmethod(lambda d: (0x40 | d))
    CMD_DIV          = staticmethod(lambda d: (0xc0 | (0x3f & (d-1))))

    CC_PORT_CID = 0
    CONFIG_CID = 1
    
    REG_SRST = 0
    REG_BASE_FREQ = 1

    def __init__(self, adapter, mux):
        chipcon.Interface.__init__(self, adapter, adapter.name)
        self.mux = RoutedPath(mux, 0xf)
        self.base_freq = int.from_bytes(
            self.mux.execute(self.CONFIG_CID, struct.pack("<B", 0x80 | self.REG_BASE_FREQ), 5)[1:],
            byteorder = 'little')

        self.logger.info("Found CC proby with internal clock of %s", metric(self.base_freq, "Hz"))
        self.__reset = False
        self.__div = 4

    @property
    def reset(self):
        return self.__reset

    @reset.setter
    def reset(self, value):
        if self.__reset == bool(value):
            return

        if self.__reset and not value:
            self.logger.info("toggling reset pin")
            cmds = bytes([self.CMD_DIV(0x40), self.CMD_RESET])
            self.mux.execute(self.CC_PORT_CID, cmds, 2)

        self.__reset = bool(value)
        
    @property
    def freq(self):
        return self.base_freq / self.__div / 2

    @freq.setter
    def freq(self, freq):
        if not freq:
            freq = self.base_freq
        self.__div = min(0x40, max(1, int(self.base_freq / float(freq) / 2)))
        self.logger.info("Divisor now %d", self.__div)

    def _execute(self, operation_list):
        ops = list(operation_list)

        commands = []
        response_lengths = []
        for op in ops:
            if isinstance(op, chipcon.DebugInit):
                commands.append(bytes([self.CMD_DIV(0x40), self.CMD_ACQUIRE,
                                       self.CMD_WAIT(0x3f), self.CMD_DIV(self.__div)]))
                response_lengths.append(4)

            elif isinstance(op, chipcon.Command):
                commands.append(bytes([self.CMD_CMD(len(op.command), op.rlen, op.should_wait)])
                                + op.command)
                op.__offset = sum(response_lengths) + 1
                response_lengths.append(op.rlen + 1)

            elif isinstance(op, chipcon.BurstWrite):
                assert 1 <= len(op.data) <= 2048
                c = (len(op.data) & 0x2ff) | 0x8000
                blob = c.to_bytes(2, "big") + bytes(op.data)
                for off in range(0, len(blob), 4):
                    last = off + 4 >= len(blob)
                    chunk = blob[off : off + 4]
                    commands.append(bytes([self.CMD_CMD(len(chunk), int(last), last)]
                                          + list(chunk)))
                    response_lengths.append(1 + int(last))

            elif isinstance(op, chipcon.Wait):
                cycles = op.cycles * 2 // 64
                commands.append(bytes([self.CMD_DIV(64)]))
                response_lengths.append(1)
                while cycles:
                    taken = min(0x40, cycles)
                    commands.append(bytes([self.CMD_WAIT(taken - 1)]))
                    response_lengths.append(1)
                    cycles -= taken
                commands.append(bytes([self.CMD_DIV(self.__div)]))
                response_lengths.append(1)

            else:
                raise base.ProtocolError("Unknown CC operation %s" % type(op))

        rsp = b''
        cmd = b''
        rsp_len = 0
        for i, (c, r) in enumerate(zip(commands, response_lengths)):
            cmd += c
            rsp_len += r

            if len(cmd) > 2000 or rsp_len > 2000 or i == len(commands) - 1:
                rsp += self.mux.execute(self.CC_PORT_CID, cmd, rsp_len)
                cmd = b''
                rsp_len = 0

        for op in ops:
            if isinstance(op, chipcon.Command):
                op.data = rsp[op.__offset:op.__offset + op.rlen]

class ProbyAdapter(basic.Adapter):
    base_path = os.path.join(os.path.dirname(__file__), "fw")
    supported_interfaces = ["swd", "swd-pt", "jtag", "jtag-int", "spi", "cc"]
    
    def reprogram(self, mode):
        """
        Loads a design into proby. Try to optimize not reloading by
        first doing an internal cache of last loaded design, and also
        try to check UserID register with a magic value.
        
        :param str mode: Base name of design bitstream
        """
        from ...component.xilinx.spartan6 import Spartan6

        self.logger.info("Reprogramming FPGA to use mode %s", mode)

        filename = os.path.join(self.base_path, mode + ".bit.gz")
        obj = Program.from_file(filename)
                 
        self.logger.info("Using internal chain of Proby, starting discovery")

        jtag_intf = basic.Adapter.open(self, "jtag", channel = "B", resetn_pin = 9, name = "pint-"+self.serial_number)
        jtag_intf.logger.setLevel(logging.WARNING)
        jtag_intf.start()
        fpga, = jtag_intf.children_of_class(Spartan6)

        self.logger.info("Got FPGA in chain: %s", fpga)

        fpga.load(obj)

        jtag_intf.close()

    def open(self, interface_name):
        if interface_name == "spi":
            self.reprogram("jtag_swd_raw")
            return basic.Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                csn_pin = 3,
                                gpio_output = 0x061b, gpio_value = 0x0210)

        elif interface_name == "jtag":
            self.reprogram("jtag_swd_raw")
            return basic.Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                gpio_output = 0x061b, gpio_value = 0x0210)

        elif interface_name == "jtag-int":
            return basic.Adapter.open(self, "jtag", channel = "B", resetn_pin = 9)

        elif interface_name == "swd-pt":
            self.reprogram("jtag_swd_raw")
            return basic.Adapter.open(self, "swd", channel = "A",
                                resetn_pin = 8,
                                oe_pin = 5,
                                gpio_output = 0x063b, gpio_value = 0x0610)

        elif interface_name == "swd":
            self.reprogram("swd_dp")

            fifo = self.device.open(interface = "A", mode = "ft245_sync_fifo")

            mux = MsgMux(fifo)
            mux.reset()

            return SwdInterface(self, mux)

        elif interface_name == "i2c":
            self.reprogram("i2c_master")

            fifo = self.device.open(interface = "A", mode = "ft245_sync_fifo")

            mux = MsgMux(fifo)
            mux.reset()

            return I2cInterface(self, mux)

        elif interface_name == "cc":
            self.reprogram("cc_master")

            fifo = self.device.open(interface = "A", mode = "ft245_sync_fifo")

            mux = MsgMux(fifo)
            mux.reset()

            return CcInterface(self, mux)

        else:
            raise ValueError("Unknown interface name: %s" % interface_name)
        
@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = ProbyAdapter

    def __init__(self, **kwargs):
        basic.AdapterEnumerator.__init__(self, "Proby", "proby",
                                        vid = 0x10eb, pid = 0x0026, **kwargs)

    def serial_mangle(self, serial):
        return str(int(serial.split(";")[-1]))
