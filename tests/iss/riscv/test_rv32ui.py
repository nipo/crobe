from crobe.loadable.elf import ElfProgram
from crobe.component.riscv.iss import rv32i
from crobe import iss
import unittest
from pathlib import Path

rv_dir = Path(__file__).parent

class ValidatorSegment:
    def __init__(self, address, data):
        self.address = address
        self.data = data

    @property
    def size(self):
        return len(self.data)

class ValidatorMemory(iss.Memory):
    def __init__(self, binary, zones):
        self.segments = []
        for addr, size in zones:
            s = ValidatorSegment(addr, binary.read(addr, size))
            self.segments.append(s)

    def segment_lookup(self, address, bit_size):
        address &= 0xffffffff

        if bit_size & 7:
            raise ValueError(bit_size)
        byte_count = bit_size // 8
        for s in self.segments:
            if s.address <= address and address + byte_count <= s.address + s.size:
                return s, address - s.address, byte_count
        raise ValueError(f"Unmapped address {address:#010x}")
            
    def load(self, address, bit_size, *, signed = False):
        segment, offset, byte_count = self.segment_lookup(address, bit_size)
        blob = segment.data[offset : offset + byte_count]
        v = int.from_bytes(blob, "little", signed = signed)
        v &= (1 << bit_size) - 1
        return v

    def store(self, address, bit_size, value):
        segment, offset, byte_count = self.segment_lookup(address, bit_size)
        v = int(value) & (1 << bit_size) - 1
        blob = v.to_bytes(byte_count, "little")
        segment.data[offset : offset + byte_count] = blob

class ValidationEnd(iss.IssException):
    pass

class ValidationTimeout(ValidationEnd):
    pass

class ValidationFailure(ValidationEnd):
    pass

class ValidationSuccess(ValidationEnd):
    pass
        
class ValidatorCpu(rv32i.RV32I):
    def unimplemented(self, opcode):
        raise ValidationFailure(f"Unimplemented opcode {opcode:#010x} at {self.registers['pc']:#010x}")

    def ecall(self):
        if self.x17 == 0x5d:
            return self.exit(self.x10)
        raise ValidationFailure(f"Unknown ecall {self.x17:#x}")

    def exit(self, rv):
        if rv == 0:
            raise ValidationSuccess()
        else:
            raise ValidationFailure(f"Exit {rv}")
    
    def ebreak(self):
        raise ValidationFailure(f"ebreak called")

class InstructionTestCase(unittest.TestCase):
    program_name = None

    def test_instruction(self):
        if self.program_name is None:
            return

        filename = rv_dir / "riscv_tests_binaries" / self.program_name
        program = ElfProgram(filename)
        memory = ValidatorMemory(program, [
            (0x80000000, 0x4000),
            (0xc0000000, 0x1000),
        ])
        program.close()
        cpu = ValidatorCpu(memory = memory)

        with self.assertRaises(ValidationSuccess) as _:
            cpu.run(max_cycles = 32768,
                    pc = 0x80000000,
                    sp = 0xc0001000)
            raise ValidationTimeout()

class Add(InstructionTestCase):
    program_name = "rv32ui-p-add"

class Addi(InstructionTestCase):
    program_name = "rv32ui-p-addi"

class And(InstructionTestCase):
    program_name = "rv32ui-p-and"

class Andi(InstructionTestCase):
    program_name = "rv32ui-p-andi"

class Auipc(InstructionTestCase):
    program_name = "rv32ui-p-auipc"

class Beq(InstructionTestCase):
    program_name = "rv32ui-p-beq"

class Bge(InstructionTestCase):
    program_name = "rv32ui-p-bge"

class Bgeu(InstructionTestCase):
    program_name = "rv32ui-p-bgeu"

class Blt(InstructionTestCase):
    program_name = "rv32ui-p-blt"

class Bltu(InstructionTestCase):
    program_name = "rv32ui-p-bltu"

class Bne(InstructionTestCase):
    program_name = "rv32ui-p-bne"

class FenceI(InstructionTestCase):
    program_name = "rv32ui-p-fence_i"

class Jal(InstructionTestCase):
    program_name = "rv32ui-p-jal"

class Jalr(InstructionTestCase):
    program_name = "rv32ui-p-jalr"

class Lb(InstructionTestCase):
    program_name = "rv32ui-p-lb"

class Lbu(InstructionTestCase):
    program_name = "rv32ui-p-lbu"

class Lh(InstructionTestCase):
    program_name = "rv32ui-p-lh"

class Lhu(InstructionTestCase):
    program_name = "rv32ui-p-lhu"

class Lui(InstructionTestCase):
    program_name = "rv32ui-p-lui"

class Lw(InstructionTestCase):
    program_name = "rv32ui-p-lw"

class MaData(InstructionTestCase):
    program_name = "rv32ui-p-ma_data"

class Or(InstructionTestCase):
    program_name = "rv32ui-p-or"

class Ori(InstructionTestCase):
    program_name = "rv32ui-p-ori"

class Sb(InstructionTestCase):
    program_name = "rv32ui-p-sb"

class Sh(InstructionTestCase):
    program_name = "rv32ui-p-sh"

class Simple(InstructionTestCase):
    program_name = "rv32ui-p-simple"

class Sll(InstructionTestCase):
    program_name = "rv32ui-p-sll"

class Slli(InstructionTestCase):
    program_name = "rv32ui-p-slli"

class Slt(InstructionTestCase):
    program_name = "rv32ui-p-slt"

class Slti(InstructionTestCase):
    program_name = "rv32ui-p-slti"

class Sltiu(InstructionTestCase):
    program_name = "rv32ui-p-sltiu"

class Sltu(InstructionTestCase):
    program_name = "rv32ui-p-sltu"

class Sra(InstructionTestCase):
    program_name = "rv32ui-p-sra"

class Srai(InstructionTestCase):
    program_name = "rv32ui-p-srai"

class Srl(InstructionTestCase):
    program_name = "rv32ui-p-srl"

class Srli(InstructionTestCase):
    program_name = "rv32ui-p-srli"

class Sub(InstructionTestCase):
    program_name = "rv32ui-p-sub"

class Sw(InstructionTestCase):
    program_name = "rv32ui-p-sw"

class Xor(InstructionTestCase):
    program_name = "rv32ui-p-xor"

class Xori(InstructionTestCase):
    program_name = "rv32ui-p-xori"
