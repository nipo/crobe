from ....iss import Iss
from functools import wraps

__all__ = ["BaseIntegerInstructionSet"]

def op(opcode):
    return opcode & 0x0000007f

def op_func3(opcode):
    return opcode & 0x0000707f

def op_r(opcode):
    return opcode & 0xfe00707f

def op_all(opcode):
    return opcode

def op_j_form(f):
    @wraps(f)
    def wrapper(self, opcode):
        rd, imm = self._j_decode(opcode)
        return f(self, rd, imm)
    return wrapper

def op_r_form(f):
    @wraps(f)
    def wrapper(self, opcode):
        rd, rs1, rs2 = self._r_decode(opcode)
        return f(self, rd, rs1, rs2)
    return wrapper

def op_r_reg_reg(f):
    @wraps(f)
    def wrapper(self, opcode):
        rd, rs1, rs2 = self._r_decode(opcode)
        l, r = self.registers[f"x{rs1}"], self.registers[f"x{rs2}"]
        value = f(self, l, r)
        if rd:
            self.registers[f"x{rd}"] = value
        self.pc_next()
    return wrapper

def op_r_reg_imm(f):
    @wraps(f)
    def wrapper(self, opcode):
        rd, rs1, rs2 = self._r_decode(opcode)
        value = f(self, self.registers[f"x{rs1}"], rs2)
        if rd:
            self.registers[f"x{rd}"] = value
        self.pc_next()
    return wrapper

def op_i_form(f):
    @wraps(f)
    def wrapper(self, opcode):
        rd, rs1, imm = self._i_decode(opcode)
        return f(self, rd, rs1, imm)
    return wrapper

def op_i_reg_imm(f):
    @wraps(f)
    def wrapper(self, opcode):
        rd, rs1, imm = self._i_decode(opcode)
        value = f(self, self.registers[f"x{rs1}"], imm)
        if rd:
            self.registers[f"x{rd}"] = value
        self.pc_next()
    return wrapper

def op_u_imm(f):
    @wraps(f)
    def wrapper(self, opcode):
        rd, imm = self._u_decode(opcode)
        value = f(self, imm)
        if rd:
            self.registers[f"x{rd}"] = value
        self.pc_next()
    return wrapper

def op_b_form(f):
    @wraps(f)
    def wrapper(self, opcode):
        rs1, rs2, imm = self._b_decode(opcode)
        return f(self, imm, rs1, rs2)
    return wrapper

def op_s_form(f):
    @wraps(f)
    def wrapper(self, opcode):
        rs1, rs2, imm = self._s_decode(opcode)
        return f(self, rs1, rs2, imm)
    return wrapper

def op_s_reg_reg_imm(f):
    @wraps(f)
    def wrapper(self, opcode):
        rs1, rs2, imm = self._s_decode(opcode)
        f(self, self.registers[f"x{rs1}"], self.registers[f"x{rs2}"], imm)
        self.pc_next()
    return wrapper

class BaseIntegerInstructionSet(Iss):
    """
    Base RiscV instruction set. Does not define XLEN or registers. See RV32I, RV64I and RV32E below.
    """
    
    @property
    def xlen_mask(self):
        return (1 << self.xlen) - 1
        
    @Iss.encoding(op, 0x37)
    @op_u_imm
    def __op_lui(self, imm):
        return imm

    @Iss.encoding(op, 0x17)
    @op_u_imm
    def __op_auipc(self, imm):
        return self.pc + imm

    @Iss.encoding(op, 0x6f)
    @op_j_form
    def __op_jal(self, rd, imm):
        old_pc = self.pc
        self.pc_next()
        if rd:
            self.registers[f"x{rd}"] = self.pc
        self.pc = old_pc + imm

    @Iss.encoding(op_func3, 0x0067)
    @op_i_form
    def __op_jalr(self, rd, rs1, imm):
        target = (self.registers[f"x{rs1}"] + imm) & ~1
        self.pc_next()
        if rd:
            self.registers[f"x{rd}"] = self.pc
        self.pc = target
        
    def __signed(self, value):
        """
        Make XLEN-bit value a python signed number
        """
        msb = 1 << (self.xlen - 1)
        return (value ^ msb) - msb

    def __op_branch(self, opcode, predicate):
        """
        Generic branch evaluator
        """
        rs1, rs2, imm = self._b_decode(opcode)
        src1 = self.registers[f"x{rs1}"]
        src2 = self.registers[f"x{rs2}"]
        if predicate(src1, src2):
            self.pc_next(imm)
        else:
            self.pc_next()

    @Iss.encoding(op_func3, 0x0063)
    def __op_beq(self, opcode):
        return self.__op_branch(opcode, lambda rs1, rs2: rs1 == rs2)

    @Iss.encoding(op_func3, 0x1063)
    def __op_bne(self, opcode):
        return self.__op_branch(opcode, lambda rs1, rs2: rs1 != rs2)

    @Iss.encoding(op_func3, 0x4063)
    def __op_blt(self, opcode):
        return self.__op_branch(opcode, lambda rs1, rs2: self.__signed(rs1) < self.__signed(rs2))

    @Iss.encoding(op_func3, 0x5063)
    def __op_bge(self, opcode):
        return self.__op_branch(opcode, lambda rs1, rs2: self.__signed(rs1) >= self.__signed(rs2))

    @Iss.encoding(op_func3, 0x6063)
    def __op_bltu(self, opcode):
        return self.__op_branch(opcode, lambda rs1, rs2: rs1 < rs2)

    @Iss.encoding(op_func3, 0x7063)
    def __op_bgeu(self, opcode):
        return self.__op_branch(opcode, lambda rs1, rs2: rs1 >= rs2)

    @Iss.encoding(op_func3, 0x0003)
    @op_i_reg_imm
    def __op_lb(self, rs1, imm):
        value = self.memory.load(rs1 + imm, 8, signed = True)
        return Iss.sign_extend(value, 8, self.xlen)

    @Iss.encoding(op_func3, 0x1003)
    @op_i_reg_imm
    def __op_lh(self, rs1, imm):
        value = self.memory.load(rs1 + imm, 16, signed = True)
        return Iss.sign_extend(value, 16, self.xlen)

    @Iss.encoding(op_func3, 0x2003)
    @op_i_reg_imm
    def __op_lw(self, rs1, imm):
        return self.memory.load(rs1 + imm, 32)

    @Iss.encoding(op_func3, 0x4003)
    @op_i_reg_imm
    def __op_lbu(self, rs1, imm):
        return self.memory.load(rs1 + imm, 8)

    @Iss.encoding(op_func3, 0x5003)
    @op_i_reg_imm
    def __op_lhu(self, rs1, imm):
        return self.memory.load(rs1 + imm, 16)

    @Iss.encoding(op_func3, 0x0023)
    @op_s_reg_reg_imm
    def __op_sb(self, rs1, rs2, imm):
        self.memory.store(rs1 + imm, 8, rs2)

    @Iss.encoding(op_func3, 0x1023)
    @op_s_reg_reg_imm
    def __op_sh(self, rs1, rs2, imm):
        self.memory.store(rs1 + imm, 16, rs2)

    @Iss.encoding(op_func3, 0x2023)
    @op_s_reg_reg_imm
    def __op_sw(self, rs1, rs2, imm):
        self.memory.store(rs1 + imm, 32, rs2)
        
    @Iss.encoding(op_func3, 0x0013)
    @op_i_reg_imm
    def __op_addi(self, rs1, imm):
        return rs1 + imm

    @Iss.encoding(op_func3, 0x2013)
    @op_i_reg_imm
    def __op_slti(self, rs1, imm):
        return int(self.__signed(rs1) < self.__signed(imm))

    @Iss.encoding(op_func3, 0x3013)
    @op_i_reg_imm
    def __op_sltiu(self, rs1, imm):
        return int(rs1 < imm)

    @Iss.encoding(op_func3, 0x4013)
    @op_i_reg_imm
    def __op_xori(self, rs1, imm):
        return rs1 ^ imm

    @Iss.encoding(op_func3, 0x6013)
    @op_i_reg_imm
    def __op_ori(self, rs1, imm):
        return rs1 | imm

    @Iss.encoding(op_func3, 0x7013)
    @op_i_reg_imm
    def __op_andi(self, rs1, imm):
        return rs1 & imm

    @Iss.encoding(op_r, 0x00001013)
    @op_r_reg_imm
    def __op_slli(self, rs1, rs2):
        return rs1 << rs2

    @Iss.encoding(op_r, 0x00005013)
    @op_r_reg_imm
    def __op_srli(self, rs1, rs2):
        return rs1 >> rs2

    @Iss.encoding(op_r, 0x40005013)
    @op_r_reg_imm
    def __op_srai(self, rs1, rs2):
        rs2 &= 0x1f
        return Iss.sign_extend(rs1 >> rs2,
                               self.xlen - rs2,
                               self.xlen)

    @Iss.encoding(op_r, 0x00000033)
    @op_r_reg_reg
    def __op_add(self, rs1, rs2):
        return rs1 + rs2

    @Iss.encoding(op_r, 0x40000033)
    @op_r_reg_reg
    def __op_sub(self, rs1, rs2):
        return rs1 - rs2

    @Iss.encoding(op_r, 0x00001033)
    @op_r_reg_reg
    def __op_sll(self, rs1, rs2):
        return rs1 << (rs2 & 0x1f)

    @Iss.encoding(op_r, 0x00002033)
    @op_r_reg_reg
    def __op_slt(self, rs1, rs2):
        return int(self.__signed(rs1) < self.__signed(rs2))

    @Iss.encoding(op_r, 0x00003033)
    @op_r_reg_reg
    def __op_sltu(self, rs1, rs2):
        return int(rs1 < rs2)

    @Iss.encoding(op_r, 0x00004033)
    @op_r_reg_reg
    def __op_xor(self, rs1, rs2):
        return rs1 ^ rs2

    @Iss.encoding(op_r, 0x00005033)
    @op_r_reg_reg
    def __op_srl(self, rs1, rs2):
        return rs1 >> (rs2 & 0x1f)

    @Iss.encoding(op_r, 0x40005033)
    @op_r_reg_reg
    def __op_sra(self, rs1, rs2):
        rs2 &= 0x1f
        return Iss.sign_extend(rs1 >> rs2,
                               self.xlen - rs2,
                               self.xlen)

    @Iss.encoding(op_r, 0x00006033)
    @op_r_reg_reg
    def __op_or(self, rs1, rs2):
        return rs1 | rs2

    @Iss.encoding(op_r, 0x00007033)
    @op_r_reg_reg
    def __op_and(self, rs1, rs2):
        return rs1 & rs2

    @Iss.encoding(op_all, 0x00000073)
    def __op_ecall(self, opcode):
        self.ecall()

    @Iss.encoding(op_all, 0x00100073)
    def __op_ebreak(self, opcode):
        self.ebreak()

    @Iss.encoding(op, 0x0f)
    def __op_fence(self, opcode):
        self.fence()
        self.pc_next()

    def ecall(self):
        """
        ECALL instruction handler stub
        """
        ...

    def ebreak(self):
        """
        EBREAK instruction handler stub
        """
        ...

    def fence(self):
        """
        FENCE instruction handler stub
        """
        ...
        
    
    @classmethod
    def _r_decode(cls, opcode):
        return cls.imm_decode(opcode, [(7, 11)]), \
            cls.imm_decode(opcode, [(15, 19)]), \
            cls.imm_decode(opcode, [(20, 24)])
        
    @classmethod
    def _i_decode(cls, opcode):
        return cls.imm_decode(opcode, [(7, 11)]), \
            cls.imm_decode(opcode, [(15, 19)]), \
            cls.imm_decode(opcode, [(20, 31)], sign_extend_to = 32)
        
    @classmethod
    def _s_decode(cls, opcode):
        return cls.imm_decode(opcode, [(15, 19)]), \
            cls.imm_decode(opcode, [(20, 24)]), \
            cls.imm_decode(opcode, [(7, 11), (25, 31)], sign_extend_to = 32)
        
    @classmethod
    def _b_decode(cls, opcode):
        return cls.imm_decode(opcode, [(15, 19)]), \
            cls.imm_decode(opcode, [(20, 24)]), \
            cls.imm_decode(opcode, [(None, 1), (8, 11), (25, 30), (7, 7), (31, 31)], sign_extend_to = 32)
        
    @classmethod
    def _u_decode(cls, opcode):
        return cls.imm_decode(opcode, [(7, 11)]), \
            cls.imm_decode(opcode, [(None, 12), (12, 31)])

    @classmethod
    def _j_decode(cls, opcode):
        return cls.imm_decode(opcode, [(7, 11)]), \
            cls.imm_decode(opcode, [(None, 1), (21, 30), (20, 20), (12, 19), (31, 31)], sign_extend_to = 32)

    def pc_next(self, increment = 4):
        self.pc += increment
