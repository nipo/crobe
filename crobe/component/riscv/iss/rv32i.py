from ....iss import Register
from . import integer

class RV32I(integer.BaseIntegerInstructionSet):
    """
    RV32I Isa implementation.

    Brings 32 GPRs x0 - x31 and PC as 32-bit registers and their ABI aliases.

    Handles all the RiscV base instruction set.
    """
    x0 = Register(32, "zero", read_only = True)
    x1 = Register(32, "ra")
    x2 = Register(32, "sp")
    x3 = Register(32, "gp")
    x4 = Register(32, "tp")
    x5 = Register(32, "t0")
    x6 = Register(32, "t1")
    x7 = Register(32, "t2")
    x8 = Register(32, "s0", "fp")
    x9 = Register(32, "s1")
    x10 = Register(32, "a0")
    x11 = Register(32, "a1")
    x12 = Register(32, "a2")
    x13 = Register(32, "a3")
    x14 = Register(32, "a4")
    x15 = Register(32, "a5")
    x16 = Register(32, "a6")
    x17 = Register(32, "a7")
    x18 = Register(32, "s2")
    x19 = Register(32, "s3")
    x20 = Register(32, "s4")
    x21 = Register(32, "s5")
    x22 = Register(32, "s6")
    x23 = Register(32, "s7")
    x24 = Register(32, "s8")
    x25 = Register(32, "s9")
    x26 = Register(32, "s10")
    x27 = Register(32, "s11")
    x28 = Register(32, "t3")
    x29 = Register(32, "t4")
    x30 = Register(32, "t5")
    x31 = Register(32, "t6")
    pc = Register(32)

    xlen = 32
