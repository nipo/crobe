from ...model import PortComponent
from ... import bitfield
from ..model import Bus, MemoryAccessFailure

class Operation:
    byte_count = 1
    is_read = False

class Read32(Operation):
    byte_count = 4
    is_read = True
    read_mask = 0xffffffff

    def __init__(self, addr):
        self.addr = addr

class Write32(Operation):
    byte_count = 4

    def __init__(self, addr, data):
        self.addr = addr
        self.data = data

class Read16(Operation):
    byte_count = 2
    is_read = True
    read_mask = 0xffff
    
    def __init__(self, addr):
        self.addr = addr

class Write16(Operation):
    byte_count = 2

    def __init__(self, addr, data):
        self.addr = addr
        self.data = data

class Read8(Operation):
    byte_count = 1
    is_read = True
    read_mask = 0xff

    def __init__(self, addr):
        self.addr = addr

class Write8(Operation):
    byte_count = 1

    def __init__(self, addr, data):
        self.addr = addr
        self.data = data

class Sbcs(bitfield.Bitfield):
    access_sizes = bitfield.Field(0, 5)
    asize = bitfield.Field(5, 7)
    error = bitfield.MappingField(12, 3, ["OK", "Timeout", "Bad", "Alignment", "Unsup", "Unk5", "Unk6", "Other"])
    readondata = bitfield.BooleanField(15)
    autoinc = bitfield.BooleanField(16)
    access = bitfield.Log2Field(17, 3, log_offset = 3)
    readonaddr = bitfield.BooleanField(20)
    busy = bitfield.BooleanField(21)
    version = bitfield.Field(29, 3)
        
class SystemBusAccess(PortComponent, Bus):
    def __init__(self, dm):
        super().__init__(dm, "SystemBus")

    def start(self):
        sbcs = Sbcs(all = self.port.read(self.port.REG_SBCS))
        self.version = sbcs.version
        self.asize = sbcs.asize
        self.dsizes = set()
        for i in range(5):
            if (sbcs.access_sizes >> i) & 1:
                self.dsizes.add(8 * (2 ** i))

        self.logger.note("System bus v. %d, %d address bits, data: %s",
                         self.version, self.asize, self.dsizes)

    def execute(self, commands):
        pending = []
        commands = list(commands)
        sbcs = 0xffffffff
        sbaddr = None
        autoread = None
        rx_map = {}

        for cno, c in enumerate(commands):
            if cno+1 < len(commands):
                cn = commands[cno+1]
            else:
                cn = None

            sbcs_next = Sbcs()
            sbaddr_next = None

            if cn and c.addr + c.byte_count == cn.addr and c.byte_count == cn.byte_count:
                sbcs_next.autoinc = True
                sbcs_next.readondata = c.is_read and cn.is_read
            elif cn and c.addr == cn.addr and c.byte_count == cn.byte_count:
                sbcs_next.autoinc = False
                sbcs_next.readondata = c.is_read and cn.is_read
            else:
                sbcs_next.autoinc = False
                sbcs_next.readondata = False
            sbcs_next.access = 8 * c.byte_count
            sbcs_next.readonaddr = c.is_read
            sbaddr_next = c.addr

            if int(sbcs_next) != int(sbcs):
                w = self.port.cmd_write(self.port.REG_SBCS,
                                        sbcs_next)
                pending.append(w)
                sbcs = sbcs_next

            if sbaddr != sbaddr_next \
               or (c.is_read and (c.byte_count, c.addr) != autoread):

                for i in range((self.asize + 31) // 32 - 1, -1, -1):
                    w = self.port.cmd_write(self.port.REG_SBADDRESS(i),
                                            sbaddr_next >> (32 * i))
                    pending.append(w)
                sbaddr = sbaddr_next

            if c.is_read:
                m = []
                for i in range((c.byte_count + 3) // 4 - 1, -1, -1):
                    r = self.port.cmd_read(self.port.REG_SBDATA(i))
                    pending.append(r)
                    m.append(r)
                rx_map[c] = m
            else:
                for i in range((c.byte_count + 3) // 4 - 1, -1, -1):
                    w = self.port.cmd_write(self.port.REG_SBDATA(0),
                                            op.data >> (i * 32))
                    pending.append(w)

            if sbcs.autoinc:
                sbaddr += c.byte_count

            if c.is_read and sbcs.autoinc and sbcs.readondata:
                autoread = c.byte_count, sbaddr
            else:
                autoread = None

        status_read = self.port.cmd_read(self.port.REG_SBCS)
        pending.append(status_read)

        self.port.execute(pending)

        status = Sbcs(all = status_read.data)
        self.logger.trace("Status: %#10x %s", status_read.data, status)

        if status.error != "OK":
            self.port.write(self.port.REG_SBCS, Sbcs(error = 0x7))
            raise MemoryAccessFailure()
        
        for op, dm in rx_map.items():
            op.data = 0
            for d in dm:
                op.data = (op.data << 32) | d.data
            op.data &= op.read_mask

    def cmd_u32_read(self, addr):
        assert 32 in self.dsizes
        return Read32(addr)

    def cmd_u32_write(self, addr, data):
        assert 32 in self.dsizes
        return Write32(addr, data)
        
    def cmd_u16_read(self, addr):
        assert 16 in self.dsizes
        return Read16(addr)

    def cmd_u16_write(self, addr, data):
        assert 16 in self.dsizes
        return Write16(addr, data)
        
    def cmd_u8_read(self, addr):
        assert 8 in self.dsizes
        return Read8(addr)

    def cmd_u8_write(self, addr, data):
        assert 8 in self.dsizes
        return Write8(addr, data)
