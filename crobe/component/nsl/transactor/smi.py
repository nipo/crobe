from ....model import PortComponent
from ....protocol import base, smi
from collections import deque

class SmiTransactor(PortComponent):
    CMD_C45_ADDR     = 0x00
    CMD_C45_WRITE    = 0x20
    CMD_C45_READINC  = 0x40
    CMD_C45_READ     = 0x60
    CMD_C22_READ     = 0x80
    CMD_C22_WRITE    = 0xa0
    
    def __init__(self, route):
        super().__init__(route, "smi")

        self.logger.note("NSL SMI Transactor")
        
    def execute(self, operation_list):
        ops = deque(operation_list)
        max_size = 1024
        pending = deque()
        
        for op in operation_list:
            if isinstance(op, smi.C22Read):
                pending.append(([self.CMD_C22_READ | op.phyad, op.addr], 3, op))
            elif isinstance(op, smi.C45Read):
                pending.append(([self.CMD_C45_READ | op.prtad, op.devad], 3, op))
            elif isinstance(op, smi.C22Write):
                pending.append(([self.CMD_C22_WRITE | op.phyad, op.addr, op.data >> 8, op.data & 0xff], 1, None))
            elif isinstance(op, smi.C45Write):
                pending.append(([self.CMD_C45_WRITE | op.prtad, op.devad, op.data >> 8, op.data & 0xff], 1, None))
            elif isinstance(op, smi.C45Addr):
                pending.append(([self.CMD_C45_ADDR | op.prtad, op.devad, op.addr >> 8, op.addr & 0xff], 1, None))
            elif isinstance(op, smi.C45ReadInc):
                pending.append(([self.CMD_C45_READINC | op.prtad, op.devad], 3, op))
            else:
                raise base.ProtocolError("Unknown SMI operation %s" % type(op))

        cmd = bytearray(max_size)
        while pending:
            cmd_size = 0
            rsp_size = 0
            gather = []

            while pending and cmd_size < max_size - 4 and rsp_size < max_size - 4:
                op_cmd, op_rsp_size, op = pending.popleft()
                cmd[cmd_size:cmd_size+len(op_cmd)] = bytes(op_cmd)

                if op:
                    gather.append((rsp_size, op))

                cmd_size += len(op_cmd)
                rsp_size += op_rsp_size

            assert cmd_size
            try:
                in_blob = self.port.send_receive(cmd[:cmd_size])
            except:
                print(ops)
                print(pending)
                print(cmd[:cmd_size])
                print(rsp_size)
                raise

            for off, op in gather:
                op.data = int.from_bytes(in_blob[off : off + 2], "big")
