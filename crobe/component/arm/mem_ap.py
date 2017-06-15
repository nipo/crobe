from ...part_id import PartId
from . import ap
from ... import bitfield
from ... import model
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
        model.Bus.__init__(self, "Mem-AP")
        self.width = 0
        self.increment = 0
        self.csw = (self.csw & ~0x00000307) | 0x00000142
        self.csw_base = self.reg_read(self.CSW) & ~0x00000307
        self.wrap_mask = 0x3ff

        from .coresight.model import MemoryMappedComponent
        self.children.append(MemoryMappedComponent(self, self.base).cast())
    
    def execute(self, ops):
        be_to_size_l2 = {0xf: 2, 0x3: 1, 0xc: 1, 0x1: 0, 0x2: 0, 0x4: 0, 0x8: 0}
        dops = []

        for o in ops:
            o.__ops = list(o.operations(self))
            dops += o.__ops
            self.logger.debug("%s translated to %s", o, o.__ops)

        access_size_l2 = None
        address = None
        for i in range(-len(dops), 0):
            o = dops[i]

            if not o.is_read and o.addr == self.TAR:
                if o.data == address:
                    del dops[i]
                else:
                    address = o.data

            elif o.addr == self.DRW:
                size_l2 = be_to_size_l2[o.be]
                if size_l2 != access_size_l2:
                    access_size_l2 = size_l2
                    dops.insert(i, self.port.cmd_ap_write(self.CSW, self.csw_base | 0x00000000 | 0x10 | access_size_l2))

                address += 1 << access_size_l2
                if address & self.wrap_mask == 0:
                    address -= self.wrap_mask + 1

        self.port.execute(dops)

        for o in ops:
            o.update(o.__ops)

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

    def cmd_mem_read(self, address, size):
        return MemoryRead(address, data)

    def cmd_u8_read(self, address):
        return Read8(address)

    def cmd_u16_read(self, address):
        return Read16(address)

    def cmd_u32_read(self, address):
        return Read32(address)

    def cmd_u8_write(self, address, data):
        return Write8(address, data)

    def cmd_u16_write(self, address, data):
        return Write16(address, data)

    def cmd_u32_write(self, address, data):
        return Write32(address, data)

class Operation(object):
    pass
                
class AccessMode(Operation):
    pass
                
class MemoryAccess(Operation):
    def update(self, ops):
        pass
    
class ReadAccess(MemoryAccess):
    def __init__(self, address, auto_increment = True):
        self.address = address
        self.auto_increment = auto_increment

    def operations(self, ap):
        if self.auto_increment or self.size_l2 != 2:
            return [ap.cmd_write(MemAp.TAR, self.address),
                    ap.cmd_read(MemAp.DRW,
                               be = ((1 << (1 << self.size_l2)) - 1) << (self.address & 0x3))]
        else:
            return [ap.cmd_write(MemAp.TAR, self.address),
                    ap.cmd_read(MemAp.BD0,
                               be = ((1 << (1 << self.size_l2)) - 1) << (self.address & 0x3))]

    def update(self, ops):
        self.data = ops[-1].data >> (8 * (self.address & 0x3))

    def __str__(self):
        return "<MemAP %s 0x%08x>" % (self.__class__.__name__, self.address)
        
class WriteAccess(MemoryAccess):
    def __init__(self, address, data, auto_increment = True):
        self.address = address
        self.data = data
        self.auto_increment = auto_increment

    def operations(self, ap):
        if self.auto_increment or self.size_l2 != 2:
            return [ap.cmd_write(MemAp.TAR, self.address),
                    ap.cmd_write(MemAp.DRW,
                                data = self.data << (8 * (self.address & 0x3)),
                                be = ((1 << (1 << self.size_l2)) - 1) << (self.address & 0x3))]
        else:
            return [ap.cmd_write(MemAp.TAR, self.address),
                    ap.cmd_write(MemAp.BD0,
                                data = self.data << (8 * (self.address & 0x3)),
                                be = ((1 << (1 << self.size_l2)) - 1) << (self.address & 0x3))]

    def __str__(self):
        return "<MemAP %s 0x%08x 0x%08x>" % (self.__class__.__name__, self.address, self.data)

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
