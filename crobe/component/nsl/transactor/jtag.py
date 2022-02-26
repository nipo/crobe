from ....model import PortComponent
from ....protocol import base, jtag
from ....util.pretty import metric
from ....bitstring import BitString, BitStringSlice
import math
from collections import deque

class JtagTransactor(PortComponent):
    CMD_SHIFT_BYTE   = 0x00 # | 5 bits byte count -1
    CMD_SHIFT_BYTE_W = 0x40
    CMD_SHIFT_BYTE_R = 0x20
    CMD_SHIFT_BIT    = 0xe0 # | 3 bits bit count -1
    CMD_SHIFT_BIT_W  = 0x10
    CMD_SHIFT_BIT_R  = 0x08
    CMD_DR_CAPTURE   = 0x80
    CMD_IR_CAPTURE   = 0x81
    CMD_SWD_TO_JTAG  = 0x82
    CMD_DIVISOR      = 0x83 # | 8 bits divisor - 1, next byte
    CMD_SYS_RESET    = 0x84 # | 1 bit asserted
    CMD_RESET        = 0x98 # | 3 bits cycle count -1
    CMD_RTI          = 0x90 # | 3 bits cycle count -1
    CMD_RESET8       = 0xb0 # | 4 bits cycle count /8 -1
    CMD_RTI8         = 0xa0 # | 4 bits cycle count /8 -1
    
    def __init__(self, route, base_freq):
        self.base_freq = base_freq

        super().__init__(route, "jtag")

        self.logger.note("NSL JTAG Transactor with internal clock of %s", metric(self.base_freq, "Hz"))

        self.__divisor = int(self.base_freq / 1e6) - 1
        self.__rate_dirty = True
        
    def context_force_refresh(self):
        self.__rate_dirty = True
        
    def freq_update(self, freq):
        if self.base_freq is None:
            return 0
        if not freq:
            freq = 15e6
        divisor = int(math.ceil(self.base_freq / 2. / float(freq))) - 1
        self.__divisor = max(0, min(divisor, 255))
        self.__rate_dirty = True
        return self.base_freq / ((self.__divisor + 1) * 2)
        
    def execute(self, operation_list):
        ops = deque(operation_list)
        max_size = 1024
        pending = deque()
        
        for op in operation_list:
            if self.__rate_dirty:
                pending.append(([self.CMD_DIVISOR, self.__divisor], 1, None, 0))
                self.__rate_dirty = False

            if isinstance(op, jtag.CaptureDr):
                pending.append(([self.CMD_DR_CAPTURE], 1, None, 0))

            elif isinstance(op, jtag.CaptureIr):
                pending.append(([self.CMD_IR_CAPTURE], 1, None, 0))

            elif isinstance(op, jtag.Reset):
                cycles = len(op.tms)
                while cycles > 8:
                    packs = cycles // 8
                    count = min(packs, 16) - 1
                    pending.append(([self.CMD_RESET8 | count], 1, None, 0))
                    cycles -= (count + 1) * 8
                if cycles:
                    pending.append(([self.CMD_RESET | (cycles - 1)], 1, None, 0))

            elif isinstance(op, base.Reset):
                pending.append(([self.CMD_SYS_RESET | int(op.asserted)], 1, None, 0))

            elif isinstance(op, jtag.Run):
                if op.cycles == 0:
                    raise ValueError("Cannot run 0 cycles")
                cycles = op.cycles
                while cycles > 8:
                    packs = cycles // 8
                    packs = min(packs, 16)
                    pending.append(([self.CMD_RTI8 | (packs - 1)], 1, None, 0))
                    cycles -= packs * 8
                if cycles:
                    pending.append(([self.CMD_RTI | (cycles - 1)], 1, None, 0))

            elif isinstance(op, jtag.SwdToJtag):
                pending.append(([self.CMD_SWD_TO_JTAG], 1, None, 0))

            elif isinstance(op, jtag.Shift):
                shift_bytes = self.CMD_SHIFT_BYTE
                shift_bits = self.CMD_SHIFT_BIT

                if isinstance(op.tdi, int):
                    has_tdi = False
                    data = b''
                    bit_count = op.tdi
                else:
                    assert isinstance(op.tdi, (BitString, BitStringSlice))
                    has_tdi = True
                    shift_bytes |= self.CMD_SHIFT_BYTE_W
                    shift_bits |= self.CMD_SHIFT_BIT_W
                    bit_count = len(op.tdi)
                    data = bytes(op.tdi)

                if op.read_tdo:
                    shift_bytes |= self.CMD_SHIFT_BYTE_R
                    shift_bits |= self.CMD_SHIFT_BIT_R
                    op.tdo = BitString()
                    has_tdo = True
                else:
                    has_tdo = False

                while bit_count >= 8:
                    byte_count = bit_count // 8
                    byte_count = min(byte_count, 32)

                    if has_tdi:
                        pending.append(([shift_bytes | (byte_count - 1)] + list(bytes(data[:byte_count])),
                                        (1 + byte_count) if has_tdo else 1,
                                        op if has_tdo else None,
                                        byte_count * 8))
                        data = data[byte_count:]
                    else:
                        pending.append(([shift_bytes | (byte_count - 1)],
                                        (1 + byte_count) if has_tdo else 1,
                                        op if has_tdo else None,
                                        byte_count * 8))
                    bit_count -= byte_count * 8

                if bit_count:
                    if has_tdi:
                        pending.append(([shift_bits | (bit_count - 1), data[0]],
                                        2 if has_tdo else 1,
                                        op if has_tdo else None,
                                        bit_count))
                    else:
                        pending.append(([shift_bits | (bit_count - 1)],
                                        2 if has_tdo else 1,
                                        op if has_tdo else None,
                                        bit_count))

            else:
                raise base.ProtocolError("Unknown JTAG operation %s" % type(op))

        while pending:
            cmd = bytearray(max_size)
            cmd_size = 0
            rsp_size = 0
            tdo_gather = []

            while pending and cmd_size < max_size - 32 and rsp_size < max_size - 32:
                op_cmd, op_rsp_size, op_tdo_target, tdo_length = pending.popleft()
                cmd[cmd_size:cmd_size+len(op_cmd)] = bytes(op_cmd)

                if op_tdo_target:
                    tdo_gather.append((op_tdo_target, rsp_size, tdo_length))

                cmd_size += len(op_cmd)
                rsp_size += op_rsp_size

            assert cmd_size
            try:
                in_blob = self.port.execute(cmd[:cmd_size], rsp_size)
            except:
                print(ops)
                print(pending)
                print(cmd[:cmd_size])
                print(rsp_size)
                raise

            for op, offset, bit_count in tdo_gather:
                op.tdo += BitString(in_blob[offset : offset + ((bit_count + 7) // 8)], bit_count)
