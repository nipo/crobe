from ...part_id import PartId
from . import ap, dp
from ... import bitfield
from .. import model
from collections import deque
import struct

__all__ = ["MemAp"]

class Csw(bitfield.Bitfield):
    DebugSoftwareAccess = bitfield.BooleanField(31)
    SProt               = bitfield.BooleanField(30)
    MasterType          = bitfield.MappingField(29, 1, {0: "Core", 1: "Debug"})
    Allocable           = bitfield.BooleanField(28)
    Cached              = bitfield.BooleanField(27)
    Bufferable          = bitfield.BooleanField(26)
    Privileged          = bitfield.BooleanField(25)
    Port                = bitfield.MappingField(24, 1, {0: "instruction", 1: "data"})
    Prot                = bitfield.Field(24, 5)
    SPIStatus           = bitfield.BooleanField(23)
    TrInProg            = bitfield.BooleanField(7)
    DbgStatus           = bitfield.BooleanField(6)
    AddrInc             = bitfield.MappingField(4, 2, {0: "Off", 1: "Single", 2: "Packed"})
    Size                = bitfield.Log2Field(0, 2, log_offset = 3)

@ap.Ap.db.register(0x04770001,# AHB-AP
                   0x04770002,# APB-AP
                   0x04770004,# AXI-AP
)
class MemAp(ap.Ap, model.Bus):
    CSW               = 0x00

    class Csw(bitfield.Bitfield):
        size          = bitfield.Field(0, 3)
        addrinc       = bitfield.Field(4, 2)
        device_en     = bitfield.BooleanField(6)
        trn_in_prog   = bitfield.BooleanField(7)
        mode          = bitfield.Field(8, 4)
        type          = bitfield.Field(12, 4)
        mte           = bitfield.BooleanField(15)
        spiden        = bitfield.BooleanField(23)
        cache         = bitfield.Field(24, 4)
        prot_priv     = bitfield.BooleanField(28)
        prot_nonsec   = bitfield.BooleanField(29)
        prot_ins      = bitfield.BooleanField(30)
        dbgsw_en      = bitfield.BooleanField(31)

    TAR               = 0x04
    TAR_MSB           = 0x08
    DRW               = 0x0c
    BD0               = 0x10
    BD1               = 0x14
    BD2               = 0x18
    BD3               = 0x1c
    ACE_BARR          = 0x20
    BASE_MSB          = 0xf0
    CFG               = 0xf4
    CFG_BIG_ENDIAN    = 0x00000001
    CFG_LARGE_ADDRESS = 0x00000002
    CFG_LARGE_DATA    = 0x00000004
    BASE              = 0xf8

    max_freq = 8e6

    def __init__(self, dp, index = 0):
        ap.Ap.__init__(self, dp, index)

        name = {1: "AHB-AP", 2: "APB-AP", 4: "AXI-AP"}.get(self.idr & 0xf, "Mem-AP")

        self.rev = self.idr >> 28
        model.Bus.__init__(self, name + "@%d" % index)
        self.base = None

    def enable(self, enable = True):
        csw = self.csw_get()
        self.logger.debug("CSW enable, r%d: CSW before %s", self.rev, csw)

        if enable:
            if self.rev == 8:
                csw.prot_ins = True
                csw.prot_nonsec = True
                csw.prot_priv = False
                csw.cache = 0xf
                csw.device_en = True
            else:
                mode = 0

                for retry in range(3):
                    csw.dbgsw_en = True
                    self.csw_set(csw)
                    csw = self.csw_get()
                    if csw.device_en or csw.dbgsw_en:
                        break
 
#                self.logger.trace("Setting CSW MODE to %d", mode)
#                csw.mode = mode
#
#                self.logger.trace("Setting CSW PROT")
#                csw.prot_ins = False
#                csw.prot_nonsec = False
#                csw.prot_priv = False
#
#                csw.cache = 0
            self.csw_set(csw)

        else:
            self.csw_update(spiden = False, dbgsw_en = False)

        self.logger.trace("CSW after %s", self.csw_get())

    def option_set(self, opt):
        if opt.startswith("base="):
            addr = int(opt[5:], 16)
            self.base = addr
            return

        ap.Ap.option_set(self, opt)
        
    def start(self):
        from .coresight.model import MemoryMappedComponent
        self.width = 0
        self.increment = 0
        cfg = self.reg_read(self.CFG)
        self.large_data = bool(cfg & self.CFG_LARGE_DATA)
        self.large_address = bool(cfg & self.CFG_LARGE_ADDRESS)

        self.logger.trace("CSW before enable: %s", self.csw_get())

        self.enable()

        self.csw_base = self.csw_get()
        self.csw_base.size = 0
        self.csw_base.addrinc = 0
        self.csw_base.mode = 0
        if self.rev == 8:
            self.csw_base.prot_priv = False
#            self.csw_base.cache = 0xf
            self.csw_base.device_en = True
            self.csw_base.prot_ins = True
            self.csw_base.prot_nonsec = True

        self.logger.trace("CSW base: %s %08x", self.csw_base, self.csw_base.all)

        if self.large_address and self.large_data:
            self.name = self.name + " LP64"
        elif self.large_address:
            self.name = self.name + " P64"
        elif self.large_data:
            self.name = self.name + " L64"
        
        base = self.reg_read(self.BASE)
        if self.large_address and base & 2:
            base |= self.reg_read(self.BASE_MSB) << 32

        if base == 0xffffffff:
            base = None
        elif base & 2:
            if base & 1:
                base = base & ~0xfff
            else:
                base = None
        else:
            base = base & ~0xfff

        if base is None and self.port.idr == 0x6ba02477:
            self.logger.warning("No base set, forcing to 0xe00ff000")
            base = 0xe00ff000
        if base is not None:
            self.base = base

        if self.base is not None:
            self.logger.info("Base: %16x", self.base)

        self.wrap_mask = 0x3ff

        # Try 16-bit and 8-bit accesses
        csw_get_8 = self.cmd_read(MemAp.CSW)
        csw_get_16 = self.cmd_read(MemAp.CSW)
        self.port.execute([
            self.cmd_csw(size = 0),
            csw_get_8,
            self.cmd_csw(size = 1),
            csw_get_16,
        ])

        if csw_get_8.data & 3 == 2 or csw_get_16.data & 3 == 2:
            self.logger.note("This Mem-AP does not support single/dual byte accesses")
        
        if self.base is not None:
            try:
                comp = MemoryMappedComponent(self, self.base)
                comp = comp.cast()
                self.child_add(comp)
            except dp.DpAccessFailure:
                self.logger.warning("Accessing memory behind this AP failed")

        ap.Ap.start(self)

    def execute(self, transfers):
        all_transfers = list(transfers)
        be_to_size_l2 = {0xf: 2, 0x3: 1, 0xc: 1, 0x1: 0, 0x2: 0, 0x4: 0, 0x8: 0}

        chunk_size = 256
        
        for chunk_offset in range(0, len(all_transfers), chunk_size):
            transfers = all_transfers[chunk_offset : chunk_offset + chunk_size]
            operations = deque()

            address = None
            csw_dirty = True
            csw_params = dict(mode = 0, size = 2, addrinc = 1)

            self.logger.protocol("Executing %s", transfers)


            for i, t in enumerate(transfers):
                if not address:
                    address_dirty = True
                    address = t.address

                if csw_params["size"] != t.size_l2:
                    csw_params["size"] = t.size_l2
                    csw_dirty = True

                reg = MemAp.DRW

                # First, handle non-word accesses, they can only use DRW
                if t.size_l2 != 2:
                    if address != t.address:
                        address_dirty = True
                        address = t.address

                    if len(transfers) > i+1:
                        nt = transfers[i+1]
                        if nt.size_l2 == t.size_l2 and nt.address == t.address + (1 << t.size_l2):
                            csw_params["addrinc"] = 1
                            csw_dirty = True
                        elif nt.address == t.address:
                            csw_params["addrinc"] = 0
                            csw_dirty = True

                else:
                    # Word access only, they may use DRW and BDx
                    # first, see whether auto increment could be useful
                    in_16 = 0
                    incrementing = 0
                    for si, nt in enumerate(transfers[i+1:]):
                        if nt.address & ~0xf == t.address & ~0xf:
                            in_16 += 1
                        if nt.address == t.address + (si + 1) * 4:
                            incrementing += 1

                        if nt.size_l2 != 2:
                            break

                    if csw_params["addrinc"] == 0:
                        if incrementing > in_16:
                            csw_dirty = True
                            csw_params["addrinc"] = 1
                    else:
                        if incrementing < in_16:
                            csw_dirty = True
                            csw_params["addrinc"] = 0

                    if address == t.address \
                       and (i >= len(transfers) - 1 \
                            or (csw_params["addrinc"] == 1 and transfers[i + 1].address == address + 4)):
                        reg = MemAp.DRW
                    elif address <= t.address < address + 16:
                        offset = t.address - (address & ~0xf)
                        reg = MemAp.BD0 + offset
                    else:
                        address_dirty = True
                        address = t.address

                if address_dirty:
                    address_dirty = False
                    operations.append(self.cmd_write(MemAp.TAR, address & 0xffffffff))
                    if self.large_address:
                        operations.append(self.cmd_write(MemAp.TAR_MSB, address >> 32))

                if csw_dirty:
                    csw_dirty = False
                    operations.append(self.cmd_csw(**csw_params))

                if isinstance(t, ReadAccess):
                    t.__op = self.cmd_read(reg)
                    operations.append(t.__op)
                else:
                    operations.append(self.cmd_write(reg, t.data << ((t.address & 3) * 8),
                                                     t.interval))

                if csw_params["addrinc"] == 1 and reg == MemAp.DRW:
                    address += 1 << t.size_l2
                    if address & self.wrap_mask == 0:
                        address_dirty = True

            #self.logger.debug("-> translated to %s", operations)

            self.port.execute(operations)

            for t in transfers:
                if isinstance(t, ReadAccess):
                    t.data = (t.__op.data >> ((t.address & 3) * 8)) & ((1 << (8 << t.size_l2)) - 1)

    def csw_get(self):
        return self.Csw(all = self.reg_read(self.CSW))

    def csw_set(self, value):
        return self.reg_write(self.CSW, int(value))

    def csw_update(self, **kwargs):
        csw = self.csw_get()
        for k, v in kwargs.items():
            setattr(csw, k, v)
        self.csw_set(csw)

    def cmd_csw(self, **kwargs):
        csw = self.Csw(all = self.csw_base.all)
        for k, v in kwargs.items():
            setattr(csw, k, v)
        return self.cmd_write(MemAp.CSW, int(csw))

#    @property
#    def tar(self):
#        if self.large_address:
#            return self.reg_read(self.TAR) | (self.reg_read(self.TAR_MSB) << 32)
#        return self.reg_read(self.TAR)
#
#    @tar.setter
#    def tar(self, data):
#        if self.large_address:
#            self.reg_write(self.TAR_MSB, data >> 32)
#        self.reg_write(self.TAR, data & 0xffffffff)
#
#    @property
#    def cfg(self):
#        return self.reg_read(self.CFG)

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
