from ...part_id import PartId
from . import ap
from ... import bitfield
from .. import model
import struct

__all__ = ["MemAp"]

class Csw(bitfield.Register):
    name = "CSW"
    fields = [
        bitfield.EnableField("Debug software access", 31),
        bitfield.EnableField("Secure", 30),
        bitfield.BinaryField("MasterType", 29, "Core", "Debug"),
        bitfield.EnableField("Allocable", 28),
        bitfield.EnableField("Cached", 27),
        bitfield.EnableField("Bufferable", 26),
        bitfield.EnableField("Privileged", 25),
        bitfield.BinaryField("Port", 24, "instruction", "data"),
        bitfield.EnableField("Secure privileged debug", 23),
        bitfield.BinaryField("Transaction", 7, "idle", "in progress"),
        bitfield.EnableField("MEM-AP accesses", 6),
        bitfield.Field("AddrInc", (4, 5), {0: "Off", 1: "Single", 2: "Packed"}),
        bitfield.Log2ValueField("Size", (0, 2), 3),
        ]

@ap.Ap.db.register(0x04770001,# AHB-AP
                   0x04770002,# APB-AP
                   0x04770004,# AXI-AP
)
class MemAp(ap.Ap, model.Bus):
    CSW = 0x00
    TAR = 0x04
    DRW = 0x0c
    BD0 = 0x10
    BD1 = 0x14
    BD2 = 0x18
    BD3 = 0x1c
    CFG = 0xf4
    BASE = 0xf8

    def __init__(self, dp, index = 0):
        ap.Ap.__init__(self, dp, index)

        name = {1: "AHB-AP", 2: "APB-AP", 4: "AXI-AP"}.get(self.idr & 0xf, "Mem-AP")
        
        model.Bus.__init__(self, name)
        self.width = 0
        self.increment = 0
        self.csw_base = self.reg_read(self.CSW) & ~0x00000f37
        self.wrap_mask = 0x3ff

        from .coresight.model import MemoryMappedComponent
        self.child_add(MemoryMappedComponent(self, self.base).cast())
    
    def execute(self, transfers):
        transfers = list(transfers)
        be_to_size_l2 = {0xf: 2, 0x3: 1, 0xc: 1, 0x1: 0, 0x2: 0, 0x4: 0, 0x8: 0}

        address = None
        csw_dirty = True
        csw = 0x012

        operations = []

        self.logger.debug("Executing %s", transfers)

        for i, t in enumerate(transfers):
            if not address:
                address_dirty = True
                address = t.address

            if (csw & 0x7) != t.size_l2:
                csw = (csw & 0xff0) | t.size_l2
                csw_dirty = True

            reg = MemAp.DRW

            # First, handle non-word accesses, they can only use DRW
            if t.size_l2 != 2:
                if address != t.address:
                    address_dirty = True
                    address = t.address

                if len(transfers) > i+1:
                    nt = t[i+1]
                    if nt.size_l2 == t.size_l2 and nt.address == t.address + (1 << t.size_l2):
                        csw = (csw & ~0x030) | 0x10
                        csw_dirty = True
                    elif nt.address == t.address:
                        csw = (csw & ~0x030)
                        csw_dirty = True
                        
            else:
                # Word access only, they may use DRW and BDx
                # first, see whether auto increment could be useful
                in_next_16 = 0
                incrementing = 0
                for si, nt in enumerate(transfers[i+1:]):
                    if nt.address < t.address + 16:
                        in_next_16 += 1
                    if nt.address == t.address + (si + 1) * 4:
                        incrementing += 1

                    if nt.size_l2 != 2:
                        break
                    
                if csw & 0x030 == 0x000:
                    if incrementing > in_next_16:
                        csw_dirty = True
                        csw = (csw & ~0x030) | 0x010
                else:
                    if incrementing < in_next_16:
                        csw_dirty = True
                        csw = csw & ~0x030
                        
                if i+1 >= len(transfers) \
                   or (csw & 0x030 == 0x010 \
                       and address == t.address \
                       and transfers[i + 1].address == address + 4):
                    reg = MemAp.DRW
                elif address <= t.address < address + 16:
                    offset = t.address - address
                    reg = MemAp.BD0 + offset
                else:
                    address_dirty = True
                    address = t.address
                    
            if address_dirty:
                address_dirty = False
                operations.append(self.cmd_write(MemAp.TAR, address))
                
            if csw_dirty:
                csw_dirty = False
                operations.append(self.cmd_write(MemAp.CSW, self.csw_base | csw))

            if isinstance(t, ReadAccess):
                t.__op = self.cmd_read(reg)
                operations.append(t.__op)
            else:
                operations.append(self.cmd_write(reg, t.data << ((t.address & 3) * 8),
                                                 t.interval))
                
            if (csw & 0x030) >> 4 == 1 and reg == MemAp.DRW:
                address += 1 << t.size_l2

        self.logger.debug("-> translated to %s", operations)
                
        self.port.execute(operations)

        for t in transfers:
            if isinstance(t, ReadAccess):
                t.data = (t.__op.data >> ((t.address & 3) * 8)) & ((1 << (8 << t.size_l2)) - 1)

    @property
    def csw(self):
        return self.reg_read(self.CSW)

    @csw.setter
    def csw(self, data):
        self.reg_write(self.CSW, data)

    @property
    def tar(self):
        return self.reg_read(self.TAR)

    @tar.setter
    def tar(self, data):
        self.reg_write(self.TAR, data)

    @property
    def base(self):
        return self.reg_read(self.BASE) & ~0xfff

    @property
    def cfg(self):
        return self.reg_read(self.CFG)

    def cmd_u8_read(self, address):
        return Read8(address)

    def cmd_u16_read(self, address):
        return Read16(address)

    def cmd_u32_read(self, address):
        return Read32(address)

    def cmd_u8_write(self, address, data, interval = 0):
        return Write8(address, data, interval)

    def cmd_u16_write(self, address, data, interval = 0):
        return Write16(address, data, interval)

    def cmd_u32_write(self, address, data, interval = 0):
        return Write32(address, data, interval)

class Operation(object):
    pass
                
class MemoryAccess(Operation):
    def __init__(self, address):
        self.address = address

class ReadAccess(MemoryAccess):
    def __str__(self):
        return "<MemAP %s 0x%08x>" % (self.__class__.__name__, self.address)

    def __repr__(self):
        return "mem_ap.%s(0x%08x)" % (self.__class__.__name__, self.address)
    
class WriteAccess(MemoryAccess):
    def __init__(self, address, data, interval = 0):
        MemoryAccess.__init__(self, address)
        self.data = data
        self.interval = interval

    def __str__(self):
        return "<MemAP %s 0x%08x 0x%08x>" % (self.__class__.__name__, self.address, self.data)

    def __repr__(self):
        return "mem_ap.%s(0x%08x, 0x%08x)" % (self.__class__.__name__, self.address, self.data)

class Read8(ReadAccess):
    size_l2 = 0

class Read16(ReadAccess):
    size_l2 = 1

class Read32(ReadAccess):
    size_l2 = 2

class Write8(WriteAccess):
    size_l2 = 0

class Write16(WriteAccess):
    size_l2 = 1

class Write32(WriteAccess):
    size_l2 = 2
