from .... import bitfield

def nop():
    return 0xe1a00000

class Instr(bitfield.Bitfield):
    all = bitfield.Field(0, 32)
    cond = bitfield.Field(28, 4)
    op = bitfield.Field(25, 3)
    low25 = bitfield.Field(0, 25)

class Ldstm(Instr):
    p = bitfield.BooleanField(24)
    u = bitfield.BooleanField(23)
    s = bitfield.BooleanField(22)
    w = bitfield.BooleanField(21)
    l = bitfield.BooleanField(20)
    rn = bitfield.Field(16, 4)
    register_list = bitfield.Field(0, 16)

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
    c2 = bitfield.Field(23, 5)
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
    w = bitfield.Field(21, 1)
    l = bitfield.Field(20, 1)
    rn = bitfield.Field(16, 4)
    rd = bitfield.Field(16, 4)
    addr = bitfield.Field(0, 12)

def str(rd, rn):
    """
    [rn] <- rd
    """
    return Ldstr(
        cond = 0xe,
        p = 1,
        op = 2,
        u = 1,
        rn = rn,
        rd = rd,
        ).all

def ldr(rd, rn):
    """
    rd <- [rn]
    """
    return Ldstr(
        cond = 0xe,
        p = 1,
        op = 2,
        u = 1,
        rn = rn,
        rd = rd,
        l = 1,
        ).all

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
    rn = bitfield.Field(12, 4)
    cp = bitfield.Field(8, 4)
    op2 = bitfield.Field(5, 3)
    c4 = bitfield.BooleanField(4)
    crm = bitfield.Field(0, 3)

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
    MRC pcp, op1, rd, crn, crm, op2
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
