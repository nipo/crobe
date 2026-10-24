from .... import bitfield
import enum

class Instr(bitfield.Bitfield):
    all = bitfield.Field(0, 32)
    cond = bitfield.Field(28, 4)
    op = bitfield.Field(25, 3)
    low25 = bitfield.Field(0, 25)

class B(Instr):
    link = bitfield.BooleanField(24)
    offset = bitfield.Field(0, 24)

class Ldstm(Instr):
    p = bitfield.BooleanField(24)
    u = bitfield.BooleanField(23)
    s = bitfield.BooleanField(22)
    w = bitfield.BooleanField(21)
    l = bitfield.BooleanField(20)
    rn = bitfield.Field(16, 4)
    register_list = bitfield.Field(0, 16)

class AluOp(enum.IntEnum):
    And = 0
    Eor = 1
    Sub = 2
    Rsb = 3
    Add = 4
    Adc = 5
    Sbc = 6
    Rsc = 7
    Tst = 8
    Teq = 9
    Cmp = 0xa
    Cmn = 0xb
    Orr = 0xc
    Mov = 0xd
    Bic = 0xe
    Mvn = 0xf

class Alu(Instr):
    imm = bitfield.BooleanField(25)
    alu_op = bitfield.Field(21, 4)
    s = bitfield.BooleanField(20)
    rd = bitfield.Field(12, 4)
    rn = bitfield.Field(16, 4)
    # imm = 1
    rot = bitfield.Field(8, 4)
    imm8 = bitfield.Field(0, 8)
    # imm = 0
    rm = bitfield.Field(0, 4)
    reg_shift = bitfield.BooleanField(4)
    shift = bitfield.Field(5, 2)
    ## reg_shift = 0
    shift_imm = bitfield.Field(7, 5)
    ## reg_shift = 1
    rs = bitfield.Field(8, 4)

class Shift(enum.IntEnum):
    Lsl = 0
    Lsr = 1
    Asr = 2
    Ror = 3

def imm8_encode(value):
    """
    Encode value as an 8-bit constant rotated right by twice a
    4-bit amount.
    """
    value &= 0xffffffff
    for rot in range(16):
        byte = ((value << (2 * rot)) | (value >> (32 - 2 * rot))) & 0xffffffff
        if byte < 0x100:
            return dict(
                imm = 1,
                rot = rot,
                imm8 = byte,
                )
    raise ValueError(f"Cannot encode {value:#010x} as 8-bit rotated value")

def rm_encode(rm, shift = Shift.Lsl, amount = 0):
    """
    Register operand shifted by an immediate amount.
    """
    if not 0 <= amount < 32:
        raise ValueError(f"Shift amount {amount} out of range")
    return dict(
        imm = 0,
        rm = rm,
        reg_shift = 0,
        shift = shift,
        shift_imm = amount,
        )

def movi(rd, imm8):
    return Alu(
        cond = 0xe,
        alu_op = AluOp.Mov,
        rd = rd,
        rn = 0,
        **imm8_encode(imm8)
    ).all

def mov(rd, rm, shift = Shift.Lsl, amount = 0):
    return Alu(
        cond = 0xe,
        alu_op = AluOp.Mov,
        rd = rd,
        rn = 0,
        **rm_encode(rm, shift, amount)
    ).all

def nop():
    return mov(0, 0)

def ori(rd, rn, imm8):
    return Alu(
        cond = 0xe,
        alu_op = AluOp.Orr,
        rd = rd,
        rn = rn,
        **imm8_encode(imm8)
    ).all

def addi(rd, rn, imm8):
    return Alu(
        cond = 0xe,
        alu_op = AluOp.Add,
        rd = rd,
        rn = rn,
        **imm8_encode(imm8)
    ).all
    
def ldmia(base, mask, update = False):
    return Ldstm(cond = 0xe,
                 op = 0x4,
                 l = True, # Load
                 u = True, # Up
                 w = update, # Writeback
                 rn = base,
                 register_list = mask,
    ).all

def stmia(base, mask, update = False):
    return Ldstm(cond = 0xe,
                 op = 0x4,
                 l = False, # Load
                 u = True, # Up
                 w = update, # Writeback
                 rn = base,
                 register_list = mask,
    ).all

def b(offset, link = False):
    """
    Branch by offset words, relative to the branch address + 8.
    """
    if not -(1 << 23) <= offset < (1 << 23):
        raise ValueError(f"Branch offset {offset} out of range")
    return B(cond = 0xe,
             op = 0x5,
             link = link,
             offset = offset & 0xffffff,
    ).all

class Mrs(Instr):
    c1 = bitfield.BooleanField(24)
    sbo = bitfield.Field(16, 4)
    r = bitfield.BooleanField(22)
    rd = bitfield.Field(12, 4)

def mrs(reg, spsr):
    return Mrs(
        cond = 0xe,
        op = 0x0,
        c1 = 1,
        sbo = 0xf,
        r = spsr,
        rd = reg,
    ).all

class MsrImm(Instr):
    c2 = bitfield.Field(23, 2)
    c22 = bitfield.Field(20, 2)
    r = bitfield.BooleanField(22)
    sbo = bitfield.Field(12, 4)
    field = bitfield.Field(16, 4)
    rot_imm = bitfield.Field(8, 4)
    imm8 = bitfield.Field(0, 8)

def msr_imm(im, rot, field, spsr):
    return MsrImm(
        cond = 0xe,
        op = 1,
        c2 = 2,
        c22 = 2,
        sbo = 0xf,
        r = spsr,
        imm8 = im,
        rot_imm = rot,
        field = field,
    ).all

class MsrReg(Instr):
    c2 = bitfield.Field(23, 2)
    c22 = bitfield.Field(20, 2)
    r = bitfield.BooleanField(22)
    sbo = bitfield.Field(12, 4)
    field = bitfield.Field(16, 4)
    rm = bitfield.Field(0, 4)

def msr_reg(reg, spsr):
    return MsrReg(
        cond = 0xe,
        op = 0x0,
        c2 = 2,
        c22 = 2,
        sbo = 0xf,
        r = spsr,
        rm = reg,
    ).all

class Ldstr(Instr):
    p = bitfield.Field(24, 1)
    u = bitfield.Field(23, 1)
    b = bitfield.Field(22, 1)
    w = bitfield.Field(21, 1)
    l = bitfield.Field(20, 1)
    rn = bitfield.Field(16, 4)
    rd = bitfield.Field(12, 4)
    addr = bitfield.Field(0, 12)

class Ldsth(Instr):
    p = bitfield.Field(24, 1)
    u = bitfield.Field(23, 1)
    c1 = bitfield.Field(22, 1)
    w = bitfield.Field(21, 1)
    l = bitfield.Field(20, 1)
    rn = bitfield.Field(16, 4)
    rd = bitfield.Field(12, 4)
    imm_hi = bitfield.Field(8, 4)
    c1011 = bitfield.Field(4, 4)
    imm_lo = bitfield.Field(0, 4)

def _ldst(load, byte, rd, rn, offset, post_index):
    if not -0x1000 < offset < 0x1000:
        raise ValueError(f"Offset {offset} out of range")
    return Ldstr(
        cond = 0xe,
        op = 2,
        p = 0 if post_index else 1,
        u = 1 if offset >= 0 else 0,
        b = int(byte),
        l = int(load),
        rn = rn,
        rd = rd,
        addr = abs(offset),
        ).all

def _ldsth(load, rd, rn, offset, post_index):
    if not -0x100 < offset < 0x100:
        raise ValueError(f"Offset {offset} out of range")
    return Ldsth(
        cond = 0xe,
        op = 0,
        p = 0 if post_index else 1,
        u = 1 if offset >= 0 else 0,
        c1 = 1,
        l = int(load),
        rn = rn,
        rd = rd,
        imm_hi = abs(offset) >> 4,
        c1011 = 0xb,
        imm_lo = abs(offset) & 0xf,
        ).all

# Single transfers. Without post_index, address is [rn, #offset]
# without writeback. With post_index, address is [rn], and rn is
# incremented by offset afterwards.

def str(rd, rn, offset = 0, post_index = False):
    """
    [rn] <- rd
    """
    return _ldst(False, False, rd, rn, offset, post_index)

def ldr(rd, rn, offset = 0, post_index = False):
    """
    rd <- [rn]
    """
    return _ldst(True, False, rd, rn, offset, post_index)

def strb(rd, rn, offset = 0, post_index = False):
    return _ldst(False, True, rd, rn, offset, post_index)

def ldrb(rd, rn, offset = 0, post_index = False):
    return _ldst(True, True, rd, rn, offset, post_index)

def strh(rd, rn, offset = 0, post_index = False):
    return _ldsth(False, rd, rn, offset, post_index)

def ldrh(rd, rn, offset = 0, post_index = False):
    return _ldsth(True, rd, rn, offset, post_index)

def bkpt(no = 0):
    return Instr(
        cond = 0xe,
        op = 0,
        low25 = 0x1200070
            | (int(no & 0xfff0) << 4)
            | int(no & 0xf),
        ).all

class Mcrc(Instr):
    c24 = bitfield.BooleanField(24)
    op1 = bitfield.Field(21, 3)
    move_from = bitfield.BooleanField(20)
    crn = bitfield.Field(16, 4)
    rd = bitfield.Field(12, 4)
    cp = bitfield.Field(8, 4)
    op2 = bitfield.Field(5, 3)
    c4 = bitfield.BooleanField(4)
    crm = bitfield.Field(0, 4)

def mrc(cp, op1, rd, crn, crm, op2 = 0):
    """
    Move ARM register from coprocessor
    MRC pcp, op1, rd, crn, crm, op2
    """
    return Mcrc(
        cond = 0xe,
        op = 0x7,
        op1 = op1,
        move_from = 1,
        crn = crn,
        rd = rd,
        cp = cp,
        op2 = op2,
        c4 = 1,
        crm = crm,
    ).all        

def mcr(cp, op1, rd, crn, crm, op2 = 0):
    """
    Move ARM register to coprocessor
    MCR pcp, op1, rd, crn, crm, op2
    """
    return Mcrc(
        cond = 0xe,
        op = 0x7,
        op1 = op1,
        move_from = 0,
        crn = crn,
        rd = rd,
        cp = cp,
        op2 = op2,
        c4 = 1,
        crm = crm,
    ).all        

class Mode(enum.IntEnum):
    Usr = 0x10
    Fiq = 0x11
    Irq = 0x12
    Svc = 0x13
    Abt = 0x17
    Und = 0x1b
    Sys = 0x1f

    @property
    def bank(self):
        """
        Mode owning the register bank this mode uses.
        """
        return Mode.Usr if self == Mode.Sys else self

    @property
    def banked_registers(self):
        """
        Registers this mode's bank holds. User bank holds all of
        r0-r14, other banks the ones they do not share with it.
        """
        if self.bank == Mode.Usr:
            return range(0, 15)
        if self == Mode.Fiq:
            return range(8, 15)
        return range(13, 15)

    @property
    def has_spsr(self):
        return self.bank != Mode.Usr

    @classmethod
    def banks(cls):
        return [cls.Usr, cls.Fiq, cls.Irq, cls.Svc, cls.Abt, cls.Und]

    def register_bank(self, no):
        """
        Bank holding register `no` (0-14) when in this mode.
        """
        if no in self.bank.banked_registers:
            return self.bank
        return Mode.Usr

class Psr(bitfield.Bitfield):
    all = bitfield.Field(0, 32)
    mode = bitfield.Field(0, 5)
    thumb = bitfield.BooleanField(5)
    fiq_disable = bitfield.BooleanField(6)
    irq_disable = bitfield.BooleanField(7)
    jazelle = bitfield.BooleanField(24)
