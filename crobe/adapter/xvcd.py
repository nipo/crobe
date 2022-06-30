from . import model
from ..protocol import jtag, base, pipe
from .. import bitstring
import os
import socket

__all__ = []

class SocketClosed(Exception):
    pass

@pipe.Interface.db.register("xvc")
class XvcdClient(jtag.Interface):
    def __init__(self, port):
        super().__init__(port)
        self.__state = None

    def freq_update(self, freq):
        tck_period = 1. / (freq or 1e6)
        rsp = self.port.write_read(
            b"settck:" + int(1e9 * tck_period).to_bytes(4, "little"),
            4)
        tck_period_ns = int.from_bytes(rsp, "little")
        self.__tck_period = tck_period_ns * 1e-9
        return 1 / self.__tck_period
        
    def _execute(self, operation_list):
        to_join = []
        ops = []

        max_shift_bits = 4096*8
        
        for o in operation_list:
            if isinstance(o, jtag.Shift):
                if not len(o.tdi):
                    continue
                if o.tdi and len(o.tdi) > max_shift_bits:
                    parts = []
                    for i in range(0, len(o.tdi), max_shift_bits):
                        parts.append(jtag.Shift(o.tdi[i : i + max_shift_bits], read_tdo = o.read_tdo))
                    o.__parts = parts
                    ops += parts
                    if o.read_tdo:
                        to_join.append(o)
                else:
                    ops.append(o)
            else:
                ops.append(o)

        self.logger.protocol("running %s", operation_list)

        assert self.__state in (self.STATE_RESET, self.STATE_PAUSE, self.STATE_RTI, None)
        
        while ops:
            tdi_buf = bitstring.BitString()
            tms_buf = bitstring.BitString()
            pending = []

            while ops and len(tms_buf) < 4032:
                op = ops.pop(0)
                pending.append(op)

                if isinstance(op, jtag.CaptureDr):
                    if self.__state == self.STATE_RTI:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                    elif self.__state == self.STATE_PAUSE:
                        tms_buf.append(0x7, 4)
                        tdi_buf.append(0x0, 4)
                    else:
                        raise base.ProtocolError("Bad state sequence")

                    if ops and isinstance(ops[0], jtag.Shift):
                        tms_buf.append(0x0, 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_SHIFT
                    elif ops and isinstance(ops[0], (jtag.CaptureIr, jtag.Run, jtag.CaptureDr)):
                        # Actually lie about that, this will do the same
                        self.__state = self.STATE_PAUSE
                    else:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                        self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.CaptureIr):
                    if self.__state == self.STATE_RTI:
                        tms_buf.append(0x3, 3)
                        tdi_buf.append(0x0, 3)
                    elif self.__state == self.STATE_PAUSE:
                        tms_buf.append(0xf, 5)
                        tdi_buf.append(0x0, 5)
                    else:
                        raise base.ProtocolError("Bad state sequence")

                    if ops and isinstance(ops[0], jtag.Shift):
                        tms_buf.append(0x0, 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_SHIFT
                    else:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                        self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.Run):
                    if self.__state == self.STATE_PAUSE:
                        tms_buf.append(0x3, 3)
                        tdi_buf.append(0x0, 3)
                        self.__state = self.STATE_RTI
                    elif self.__state == self.STATE_RESET:
                        tms_buf.append(0, 1)
                        tdi_buf.append(0, 1)
                        self.__state = self.STATE_RTI
                        
                    if self.__state == self.STATE_RTI:
                        if op.cycles:
                            tms_buf.append(0, op.cycles)
                            tdi_buf.append(0, op.cycles)
                    else:
                        raise base.ProtocolError("Bad state sequence")

                elif isinstance(op, jtag.GenericOperation):
                    tms_buf += op.tms
                    tdi_buf += bitstring.BitString(-1, len(op.tms))
                    self.__state = self.STATE_RESET

                elif isinstance(op, jtag.Shift):
                    if self.__state == self.STATE_PAUSE:
                        tms_buf.append(0x1, 2)
                        tdi_buf.append(0x0, 2)
                        self.__state = self.STATE_SHIFT

                    assert self.__state == self.STATE_SHIFT

                    op.__offset = len(tms_buf)
                    tdi_buf += op.tdi

                    if ops and isinstance(ops[0], jtag.Shift):
                        tms_buf.append(0, len(op.tdi))
                    elif ops and isinstance(ops[0], (jtag.CaptureIr, jtag.CaptureDr, jtag.Run)):
                        tms_buf.append(3 << (len(op.tdi) - 1), len(op.tdi) + 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_RTI
                    else:
                        tms_buf.append(1 << (len(op.tdi) - 1), len(op.tdi) + 1)
                        tdi_buf.append(0x0, 1)
                        self.__state = self.STATE_PAUSE

                elif isinstance(op, jtag.Pause):
                    pass

                elif isinstance(op, base.Reset):
                    pass

                else:
                    raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

                assert len(tms_buf) == len(tdi_buf)

            self.logger.debug("tms: %s", tms_buf)
            self.logger.debug("tdi: %s", tdi_buf)
            
            tdo_blob = self.port.write_read(
                b''.join([
                    b"shift:",
                    len(tms_buf).to_bytes(4, "little"),
                    tms_buf.data,
                    tdi_buf.data]), (len(tms_buf) + 7) // 8)

            tdo_buf = bitstring.BitString(tdo_blob, len(tms_buf))

            self.logger.debug("tdo: %s", tdo_buf)

            for idx, op in enumerate(pending):
                if isinstance(op, jtag.Shift) and op.read_tdo:
                    op.tdo = tdo_buf[op.__offset : op.__offset + len(op.tdi)]

        assert self.__state in (self.STATE_RTI, self.STATE_RESET, self.STATE_PAUSE), self.__state

        for o in to_join:
            tdo = bitstring.BitString()
            for op in o.__parts:
                tdo += op.tdo
            o.tdo = tdo
