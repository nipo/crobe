import enum
from .... import bitfield

class Register(enum.IntEnum):
    DebugCtrl        = 0x00
    DebugStatus      = 0x01
    VectorCatchCtrl  = 0x02
    CommCtrl         = 0x04
    CommData         = 0x05
    Wpt0AddrValue    = 0x08
    Wpt0AddrMask     = 0x09
    Wpt0DataValue    = 0x0a
    Wpt0DataMask     = 0x0b
    Wpt0ControlValue = 0x0c
    Wpt0ControlMask  = 0x0d
    Wpt1AddrValue    = 0x10
    Wpt1AddrMask     = 0x11
    Wpt1DataValue    = 0x12
    Wpt1DataMask     = 0x13
    Wpt1ControlValue = 0x14
    Wpt1ControlMask  = 0x15

class DebugControl(bitfield.Bitfield):
    all      = bitfield.Field(0, 32)
    dbgack   = bitfield.BooleanField(0)
    dbgrq    = bitfield.BooleanField(1)
    intdis   = bitfield.BooleanField(2)
    step     = bitfield.BooleanField(3)
    monitor  = bitfield.BooleanField(4)
    disable  = bitfield.BooleanField(5)

class CommControl(bitfield.Bitfield):
    all      = bitfield.Field(0, 32)
    version  = bitfield.Field(28, 4)
    cpu_to_debug = bitfield.BooleanField(1)
    debug_to_cpu = bitfield.BooleanField(0)

class Moe(enum.IntEnum):
    No        = 0
    Ice0Bkpt  = 1
    Ice1Bkpt  = 2
    Bkpt      = 3
    Vector    = 4
    ExtBkpt   = 5
    Ice0Watch = 6
    Ice1Watch = 7
    ExtWatch  = 8
    IntDbgReq = 9
    ExtDbgReq = 10
    Speed     = 11

class DebugStatus(bitfield.Bitfield):
    all      = bitfield.Field(0, 32)
    dbgack   = bitfield.BooleanField(0)
    dbgrq    = bitfield.BooleanField(1)
    ifen     = bitfield.BooleanField(2)
    syscomp  = bitfield.BooleanField(3)
    itbit    = bitfield.BooleanField(4)
    ijbit    = bitfield.BooleanField(5)
    moe      = bitfield.EnumField(6, 4, Moe)

class VectorCatchCtrl(bitfield.Bitfield):
    all     = bitfield.Field(0, 32)
    reset   = bitfield.BooleanField(0)
    indef   = bitfield.BooleanField(1)
    swi     = bitfield.BooleanField(2)
    p_abort = bitfield.BooleanField(3)
    d_abort = bitfield.BooleanField(4)
    irq     = bitfield.BooleanField(6)
    fiq     = bitfield.BooleanField(7)

class WatchControl(bitfield.Bitfield):
    all        = bitfield.Field(0, 32)
    write      = bitfield.BooleanField(0)
    dmas       = bitfield.Field(1, 2)
    thumb      = bitfield.BooleanField(1)
    jazelle    = bitfield.BooleanField(2)
    data       = bitfield.BooleanField(3)
    privileged = bitfield.BooleanField(4)
    dbgext     = bitfield.BooleanField(5)
    chain      = bitfield.BooleanField(6)
    range      = bitfield.BooleanField(7)
    enable     = bitfield.BooleanField(8)
