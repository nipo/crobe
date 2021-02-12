from ....protocol import jtag
from .... import bitfield
import enum

class InstructionRegistry(jtag.InstructionRegistry):
    irlen = 4

    class PathSelect(enum.IntEnum):
        Macrocell = 0
        Debug = 1
        Ice = 2
        Ext = 3
        Cp15 = 15
    SCAN_PATH_SELECT = jtag.Dr(5, type = PathSelect)

    class Debug(bitfield.Bitfield):
        all        = bitfield.Field(0, 67)
        data       = bitfield.Field(0, 32)
        wptandbkpt = bitfield.BooleanField(33)
        sysspeed   = bitfield.BooleanField(34)
        instr      = bitfield.Field(35, 32)
    DEBUG = jtag.Dr(Debug._width, type = Debug)

    class Ice(bitfield.Bitfield):
        all        = bitfield.Field(0, 38)
        write      = bitfield.BooleanField(37)
        addr       = bitfield.Field(32, 5)
        data       = bitfield.Field(0, 32)
    ICE = jtag.Dr(Ice._width, type = Ice)

    class Cp15(bitfield.Bitfield):
        all        = bitfield.Field(0, 48)
        write      = bitfield.BooleanField(47)
        op1        = bitfield.Field(44, 3)
        op2        = bitfield.Field(41, 3)
        crn        = bitfield.Field(37, 4)
        crm        = bitfield.Field(33, 4)
        access     = bitfield.BooleanField(32)
        data       = bitfield.Field(0, 32)
    CP15 = jtag.Dr(Ice._width, type = Cp15)

    IDCODE               = jtag.Instruction(0xe, "DEVICE_ID")
    EXTEST               = jtag.Instruction(0x0, "TAP_BYPASS")
    SCAN_N               = jtag.Instruction(0x2, "SCAN_PATH_SELECT")
    PRELOAD_ICE          = jtag.Instruction(0x3, "ICE")
    PRELOAD_DEBUG        = jtag.Instruction(0x3, "DEBUG")
    RESTART              = jtag.Instruction(0x4, "TAP_BYPASS")
    INTEST_ICE           = jtag.Instruction(0xc, "ICE")
    INTEST_DEBUG         = jtag.Instruction(0xc, "DEBUG")
    INTEST_CP15          = jtag.Instruction(0xc, "CP15")

class Tap(jtag.Tap, InstructionRegistry):
    def __init__(self, port, index, idcode, name):
        from . import debug

        super().__init__(port, index, idcode)
        self.name = name

        self.dbg = debug.Debug(self)
        self.child_add(self.dbg)
