from . import base
import click
from ..loadable.object import Program
import struct
import re
from ..component.riscv.iss import rv32i
from .. import iss
import time

@base.cli.group(help = "RISC-V tools")
def riscv():
    pass

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

    def segment_lookup(self, address, byte_count):
        address &= 0xffffffff

        for s in self.segments:
            if s.address <= address and address + byte_count <= s.address + s.size:
                return s, address - s.address
        raise ValueError(f"Unmapped address {address:#010x}")
            
    def read(self, address, size):
        segment, offset = self.segment_lookup(address, size)
        return segment.data[offset : offset + size]

    def write(self, address, data):
        segment, offset = self.segment_lookup(address, len(data))
        segment.data[offset : offset + len(data)] = data
    
    def load(self, address, bit_size, *, signed = False):
        if bit_size & 7:
            raise ValueError(bit_size)
        byte_count = bit_size // 8
        blob = self.read(address, bit_size // 8)
        v = int.from_bytes(blob, "little", signed = signed)
        v &= (1 << bit_size) - 1
        return v

    def store(self, address, bit_size, value):
        if bit_size & 7:
            raise ValueError(bit_size)
        byte_count = bit_size // 8

        v = int(value) & ((1 << bit_size) - 1)
        blob = v.to_bytes(byte_count, "little")
        self.write(address, blob)

class ValidationEnd(Exception):
    pass

class ValidationFailure(ValidationEnd):
    pass

class ValidationSuccess(ValidationEnd):
    pass
        
class ValidatorCpu(rv32i.RV32I):
    def unimplemented(self, opcode):
        raise ValidationFailure(f"Unimplemented opcode {opcode:#010x} at {self.registers['pc']:#010x}")

    def ecall(self):
        if self.a7 == 0x5d:
            return self.exit(self.a0)
        if self.a7 == 0:
            return self.exit(self.a0)
        if self.a7 == 1:
            message = bytes(self.memory.read(self.a0, self.a1))
            print(f"Console: '{message}'")
            self.pc_next()
            return
        raise ValidationFailure(f"Unknown ecall {self.a7:#x}")

    def exit(self, rv):
        if rv == 0:
            raise ValidationSuccess()
        else:
            raise ValidationFailure(f"Exit {rv}")
    
    def ebreak(self):
        raise ValidationFailure(f"ebreak called")
        
@riscv.command(help = "Execute program in custom VM")
@click.argument("program", type = base.PROGRAM)
@click.option("--a0", type = base.HEX, default = 0)
def validate(program, a0):
    memory = ValidatorMemory(program, [
        (0x10000000, 0x10000),
        (0x40000000, 0x1000),
    ])
    cpu = ValidatorCpu(memory = memory)

    before = time.time()
    try:
        cpu.run(max_cycles = 327680,
                pc = 0x10000000,
                sp = 0x40001000,
                a0 = a0)
        print("Too many cycles run")
        cpu.dump()

    except ValidationFailure as e:
        print(f"Fail {e}")
        cpu.dump()
        raise click.exceptions.Exit(1)

    except ValidationSuccess:
        print("OK")
    after = time.time()
    duration = after - before

    print(f"{cpu.instruction_count} instructions in {duration} sec.")
    print(f"{cpu.instruction_count / duration / 1e6:3.3f} MHz")
