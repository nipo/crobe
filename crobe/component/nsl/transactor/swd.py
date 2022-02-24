from ....model import PortComponent
from ....protocol import base, swd
from ....util.pretty import metric
import math
from collections import deque

class SwdTransactor(PortComponent):
    CMD_TURNAROUND   = 0xd0
    CMD_RUN          = 0x00
    CMD_ABORT        = 0xc0
    CMD_DIVISOR      = 0xc1
    CMD_BITBANG      = 0xe0
    CMD_READ         = 0x90
    CMD_WRITE        = 0x80
    CMD_SYS_RESET    = 0xd8

    RSP_OP_MASK          = 0xf0
    RSP_ACK_MASK         = 0x07
    RSP_PAR_ERROR        = 0x08

    def __init__(self, route, base_freq):
        self.base_freq = base_freq
        self.__turnaround_cycles = 1
        self.__turnaround_dirty = True
        super().__init__(route, 'swd')

        self.logger.info("NSL SWD Transactor with internal clock of %s", metric(self.base_freq, "Hz"))
        
        self.__divisor = int(self.base_freq / 1e6) - 1
        self.__rate_dirty = True
        
    def freq_update(self, freq):
        if self.base_freq is None:
            return 0
        if not freq:
            freq = 15e6
        divisor = math.ceil(self.base_freq / float(freq)) - 1
        self.__divisor = max(0, min(divisor, 65535))
        self.__rate_dirty = True
        return self.base_freq / ((self.__divisor + 1) * 2)
        
    def context_force_refresh(self):
        self.__turnaround_dirty = True
        self.__rate_dirty = True
    
    @property
    def turnaround_cycles(self):
        return self.__turnaround_cycles

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        self.logger.trace("Changing turnaround_cycles from %d to %d", self.__turnaround_cycles, cycles)
        if cycles != self.__turnaround_cycles:
            self.__turnaround_dirty = True
            self.__turnaround_cycles = cycles

    def execute(self, operation_list):
        ops = deque(operation_list)
        max_size = 512
        
        self.logger.trace("Running %s", operation_list)

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
                    cmd[cmd_size] = self.CMD_DIVISOR
                    cmd[cmd_size+1] = self.__divisor & 0xff
                    cmd[cmd_size+2] = self.__divisor >> 8
                    cmd_size += 3
                    rsp_size += 1
                    self.__rate_dirty = False

                if isinstance(op, swd.Read):
                    cmd[cmd_size] = self.CMD_RUN | 2
                    cmd_size += 1
                    rsp_size += 1

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
                    
#                elif isinstance(op, swd.Write) and op.addr == 0 and not op.ap and op.data == 0x1f:
#                    # Abort
#                    cmd[cmd_size] = self.CMD_ABORT
#                    cmd_size += 1
#                    rsp_size += 1
                    
                elif isinstance(op, swd.Write):
                    cmd[cmd_size] = self.CMD_RUN | 2
                    cmd_size += 1
                    rsp_size += 1

                    addr = op.addr & 0x3
                    ap = int(bool(op.ap))

                    cmd[cmd_size] = self.CMD_WRITE | (ap << 5) | addr
                    cmd[cmd_size + 1 : cmd_size + 5] = int(op.data).to_bytes(4, "little")
                    op.__offset = rsp_size
                    cmd_size += 5
                    rsp_size += 1

                    if ap:
                        cmd[cmd_size] = self.CMD_RUN | 10
                        cmd_size += 1
                        rsp_size += 1

                elif isinstance(op, base.Reset):
                    cmd[cmd_size] = self.CMD_SYS_RESET | int(op.asserted)
                    cmd_size += 1
                    rsp_size += 1
                    
                elif isinstance(op, swd.Wakeup):
                    count = op.cycles
                    while count:
                        c = min((64, count))
                        count -= c
                        cmd[cmd_size] = self.CMD_RUN | 0x40 | (c - 1)
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

                elif isinstance(op, swd.SelectionOperation):
                    out = op.out
                    for off in range(0, len(out), 32):
                        l = min(len(out) - off, 32)
                        cmd[cmd_size : cmd_size + 5] = [self.CMD_BITBANG | (l-1)] + list(bytes(out[off : off + l]))
                        cmd_size += 5
                        rsp_size += 1

                else:
                    raise base.ProtocolError("Unknown SWD operation %s" % type(op))

            in_blob = self.port.execute(cmd[:cmd_size], rsp_size)

            for idx, op in enumerate(pending):
#                if isinstance(op, swd.Write) and op.addr == 0 and not op.ap and op.data == 0x1f:
#                    op.ack = swd.Ack.OK
#                    
                if isinstance(op, (swd.Read, swd.Write)):
                    rsp = in_blob[op.__offset]
                    
                    try:
                        ack = swd.Ack(0x7 & rsp)
                    except ValueError:
                        ack = swd.Ack.INVALID

                    if ack == swd.Ack.OK and rsp & self.RSP_PAR_ERROR:
                        ack = swd.Ack.PARITY_ERR

                    op.ack = ack

                    if isinstance(op, swd.Read):
                        op.data = int.from_bytes(in_blob[op.__offset + 1 : op.__offset + 5], "little")
