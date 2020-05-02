from . import model
from .ftdi import basic
from ..loadable.object import Program
import logging
import os
import os.path
import time
from collections import deque, defaultdict
from ..util.pretty import metric
from ..model import PortComponent
from ..component.arm import dp
from ..protocol import base as pbase
from ..protocol import i2c
from ..bitstring import BitString
import threading
import struct
import time

__all__ = []

# DC590 Ascii protocol:
# D[hhhh]: Delay for N ms, N=hhhh in hex
# g: IO pin low
# G: IO pin high
# H: Wait for MISO to rise
# i: Identify, returns NUL-terminated string
# I: Controller ID string, returns NUL-terminated string
# K[vp]: Set pin p to value v; v in ['0', '1'], p is an ascii number
# L: Wait for MISO to fall
# M[m]: Set serial mode to m; m in 'I' (i2c), 'S' (spi) or 'X' (other i2c)
# p: i2c stop
# P: ping, returns 'P'
# Q: i2c byte read with ACK, returns hex byte
# r: spi read, returns hex byte
# R: spi/i2c byte read with NACK, returns hex byte
# s: i2c start
# S[xx]: Send byte (i2c/spi), returns 'N' in case of i2c NACK
# t/u: Recording loop (WTF ?)
# T[xx]: SPI send/receive byte, reutrn hex byte
# v: Return recording loop
# w: Playback mode (WTF ?)
# x: Set CS pin low
# X: Set CS pin high
# Z: Return a line feed (\n) on output stream
# 0x80: Trigger reset

def CMD_DELAY(x):
    return ('D%04X' % x).encode('ascii')
CMD_IO_LOW = b'g'
CMD_IO_HIGH = b'G'
CMD_SPI_MISO_WAIT_HIGH = b'H'
CMD_ID_BOARD = b'i'
CMD_ID_CONTROLLER = b'I'
def CMD_PIN(pin, set):
    return ('K%X%X' % (int(set), int(pin))).encode('ascii')
CMD_SPI_MISO_WAIT_LOW = b'L'
def CMD_MODE(m):
    if m == "spi":
        return b"MS"
    if m == "i2c":
        return b"MI"
    if m == "i2c-aux":
        return b"MX"
    raise ValueError(m)
CMD_I2C_STOP = b'p'
CMD_PING = b'P'
CMD_I2C_READ_ACK = b'Q'
CMD_SPI_READ = b'r'
CMD_I2C_READ_NACK = b'R'
CMD_I2C_START = b's'
def CMD_I2C_WRITE(b):
    return ('S%02X' % b).encode('ascii')
def CMD_TRANSCEIVE(b):
    return ('T%02X' % b).encode('ascii')
CMD_CS_LOW = b'x'
CMD_CS_HIGH = b'X'
CMD_LF = b'Z'
CMD_RESET = b'\x80'

class I2cInterface(i2c.Interface):
    def __init__(self, adapter):
        i2c.Interface.__init__(self, adapter, adapter.name)
        self.freq_cap("hardware", 1e5)
        
    def freq_update(self, freq):
        return 1e5

    def _execute(self, operation_list):
        ops = list(operation_list)
        cmd = []
        rsp_size = 1
        rsp_total_size = 0
        rsp = b''
        starts = []

        prev = None
        for i, cur in enumerate(ops):
            next = ops[i+1] if i < len(ops) - 1 else None

            if not prev or (isinstance(prev, i2c.Read) != isinstance(cur, i2c.Read)):
                cmd.append(CMD_I2C_START)
                starts.append((len(cmd), cur))
                cmd.append(CMD_I2C_WRITE((cur.addr << 1) | int(isinstance(cur, i2c.Read))))

            last = not next or (isinstance(cur, i2c.Read) != isinstance(next, i2c.Read))

            if isinstance(cur, i2c.Read):
                cur.__rsp = []
                for offset in range(0, cur.size):
                    cur.__rsp.append(len(cmd))
                    if last:
                        cmd.append(CMD_I2C_READ_NACK)
                    else:
                        cmd.append(CMD_I2C_READ_ACK)
        
            elif isinstance(cur, i2c.Write):
                cur.__rsp = []
                for offset in range(0, len(cur.data)):
                    cur.__rsp.append(len(cmd))
                    if last:
                        cmd.append(CMD_I2C_WRITE(cur.data[offset]))
                    else:
                        cmd.append(CMD_I2C_READ_ACK)

            else:
                raise base.ProtocolError("Unknown I2C operation %s" % type(op))

            prev = cur

        cmd.append(CMD_I2C_STOP)

        rsp = self.port._run(cmd)

        for s, op in starts:
            if rsp[s] == b'N':
                raise i2c.AddressNack(op.addr)

        for op in ops:
            data = b''.join(rsp[i] for i in op.__rsp)
            if isinstance(op, i2c.Read):
                op.data = bytes.fromhex(str(data, "ascii"))
            elif not all(x != b'N' for x in data[:-1]):
                raise i2c.DataNack()

class Dc590Adapter(basic.Adapter):
    supported_interfaces = ["i2c"]

    def __init__(self, enumerator, device):
        basic.Adapter.__init__(self, enumerator, device)

    def _run(self, commands):
        self.logger.info("<< %s" % (commands,))
        cmd = CMD_LF.join(commands)
        self.handle.write(cmd)
        rsp = self._read()
        responses = rsp.split(b'\n')
        self.logger.info(">> %s" % (responses,))
        return responses

    def _read(self, to = 1):
        rsp = b''
        last_read = time.time()
        while time.time() < last_read + to:
            r = self.handle._read(1024)
            rsp += r
            if r:
                to = .01
                last_read = time.time()
                if len(r) != 1024:
                    break
        return rsp
    
    def open(self, interface_name):
        self.handle = self.device.open(interface = "A", mode = "reset")
        self._read(.1)
        self._run([CMD_ID_BOARD, CMD_ID_CONTROLLER])

        if interface_name == "i2c":
            self._run([CMD_MODE("i2c")])
            return I2cInterface(self)

        raise ValueError("Unknown interface name: %s" % interface_name)
        
@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Dc590Adapter

    def __init__(self, **kwargs):
        basic.AdapterEnumerator.__init__(self, "LTC DC590B", "dc590b",
                                        vid = 0x0403, pid = 0x6001, **kwargs)
