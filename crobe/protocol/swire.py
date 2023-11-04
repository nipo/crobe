from . import base, pipe
from ..db import Db
from ..bitstring import BitString
from ..util.endian import bitswap8
import binascii
import struct

__all__ = ["Interface"]

class Interface(base.Interface):
    """
    Telink SWIRE protocol
    """

    # https://github.com/pvvx/TlsrTools/blob/master/DOCs/SWM_S.pdf

    db = Db("SWIRE chip type")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-SWIRE")

    def start(self):
        base.Interface.start(self)
        
    def _execute(self, ops):
        """
        Executes a row of operations.
        """
        raise NotImplementedError()

    def cmd_write(self, sid, addr, data):
        return Write(sid, addr, data)

    def cmd_read(self, sid, addr, size):
        return Read(sid, addr, size)

class Operation(object):
    def __repr__(self):
        return str(self)

class Read(Operation):
    def __init__(self, sid, address, size):
        self.sid = sid
        self.address = address
        self.size = size
        self.data = None

    def __str__(self):
        return f"<Read {self.sid} {self.address:#x} {self.size}>"

class Write(Operation):
    def __init__(self, sid, address, data):
        self.sid = sid
        self.address = address
        self.data = data

    def __str__(self):
        return f"<Write {self.sid} {self.address:#x} {self.data.hex()}>"

@pipe.Interface.db.register("swire")
class SwireUartImpl(Interface):
    def __init__(self, port):
        super().__init__(port, "swire")

    def freq_update(self, freq):
        if freq is None:
            freq = 200e3
        freq = self.port.freq_cap("swire", freq * 5)
        return freq / 5

    def lower(self, data, start = False, end = False):
        ret = []
        for byte_index, b in enumerate(data):
            bits = b << 1
            if start and byte_index == 0:
                bits |= 0x200
            if end and byte_index == len(data) - 1:
                assert b == 0xff
                bits |= 0x200
            for i in range(8,-1,-2):
                uart_byte = [0xef, 0x0f, 0xe8, 0x08][(bits >> i) & 3]
                ret.append(uart_byte)
        return bytes(ret)

    def decode(self, byte_stream):
        bitstream = BitString(-1, 1)
        for b in byte_stream:
            bits = (b << 1) | 0x200
            bitstream += BitString(bits, 10)
        bitstream += BitString(-1, 1)

        self.logger.debug("> bitstream %s", bitstream)
        
        data_bits = BitString()
        z_run = 0
        for b in bitstream:
            if b:
                if z_run:
                    data_bits += BitString(int(z_run > 2), 1)
                z_run = 0
            else:
                z_run += 1

        self.logger.debug("> data_bits %s", data_bits)
                
        start = False
        stop = False
        data_stream = []
        for bit_index in range(0, len(data_bits)-9, 10):
            bits = data_bits[bit_index : bit_index + 10]
            stop = bits[0]
            if bit_index == 0:
                start = stop
            if bits[9] != 0:
                print("Framing error")
            data_stream.append(int(bits[1:9]))
        return bitswap8(bytes(data_stream)), start, stop
                
    def _execute(self, operation_list):
        timeout = (1 / self.freq) * 5

        for op in operation_list:
            self.logger.info("- %s", op)
            if isinstance(op, Write):
                uart_stream = self.lower(struct.pack("BHB", 0x5a, op.address, op.sid) + op.data + b"\xff", start = True, end = True)
                r = pipe.Read(None)
                w = pipe.Write(uart_stream)
                self.port.execute([w, r], timeout = timeout)

            elif isinstance(op, Read):
                uart_stream = self.lower(struct.pack("BHB", 0x5a, op.address, op.sid | 0x80), start = True, end = False)
                r = pipe.Read(None)
                w = pipe.Write(uart_stream)
                self.port.execute([w, r], timeout = timeout)

                data = b''
                for _ in range(op.size):
                    r = pipe.Read(None)
                    w = pipe.Write(b"\xff")
                    self.port.execute([w, r], timeout = timeout)
                    rx_stream, start, stop = self.decode(r.data)
                    data += rx_stream
                uart_stream = self.lower(b"\xff", start = False, end = True)
#                r = pipe.Read(None)
#                w = pipe.Write(uart_stream)
#                self.port.execute([w, r], timeout = timeout)
                op.data = data

            elif isinstance(op, base.Reset):
                self.port.rts_set(op.asserted)
