from ....model import PortComponent
from ....protocol import base, chipcon

class ControlStatus(PortComponent):
    CMD_WRITE        = 0
    CMD_READ         = 0x80

    def __init__(self, route, name = "cs"):
        super().__init__(route, name)

    def reg_read(self, no):
        r = self.cmd_reg_read(no)
        self.execute([r])
        return r.value

    def reg_write(self, no, value):
        w = self.cmd_reg_write(no, value)
        self.execute([w])

    def reg_read_many(self, nos):
        cmds = [self.cmd_reg_read(no) for no in nos]
        self.execute(cmds)
        return [op.value for op in cmds]

    def reg_write_many(self, values):
        cmds = [self.cmd_reg_write(addr, value) for (addr, value) in values.items()]
        self.execute(cmds)

    def reg_write(self, no, value):
        w = self.cmd_reg_write(no, value)
        self.execute([w])

    def cmd_reg_read(self, no):
        return StatusRead(no)

    def cmd_reg_write(self, no, value):
        return ControlWrite(no, value)

    def execute(self, operation_list):
        cmd = b""
        rsp_size = 0

        for o in operation_list:
            if isinstance(o, StatusRead):
                cmd += bytes([self.CMD_READ | o.reg])
                rsp_size += 5
            elif isinstance(o, ControlWrite):
                cmd += bytes([self.CMD_WRITE | o.reg]) + int(o.value).to_bytes(4, "little")
                rsp_size += 1
            else:
                raise NotImplementedError(o)

        rsp = self.port.execute(cmd, rsp_size)

        off = 0
        for o in operation_list:
            if isinstance(o, StatusRead):
                off += 5
                o.value = int.from_bytes(rsp[off+1:off+5], 'little')
            else:
                off += 1

class Operation:
    def __init__(self, reg):
        self.reg = reg

class StatusRead(Operation):
    def __init__(self, reg):
        super().__init__(reg)
        self.value = None

    def __str__(self):
        return "<StatusRead 0x%02x>" % (self.reg,)
        
class ControlWrite(Operation):
    def __init__(self, reg, value):
        super().__init__(reg)
        self.value = value

    def __str__(self):
        return "<ControlWrite 0x%02x 0x%08x>" % (self.reg, self.value)
