import inspect
import types
from .register import *
from .exception import *

__all__ = ["Iss"]

class InstructionInfo:
    """
    Metaprog data holder used to build instruction decoder.
    """
    def __init__(self, target_function):
        self.target_function = target_function
        self.encodings = {}

    def encoding_add(self, decoder, value):
        if decoder not in self.encodings:
            self.encodings[decoder] = set([value])
        else:
            self.encodings[decoder].add(value)
            
class IssMeta(type):
    """
    Iss metaclass, merges register and instruction information from bases.
    """
    def __new__(cls, name, bases, attrs, **kwargs):
        instruction_infos = []
        register_infos = {}

        for b in bases:
            try:
                ii = b._instruction_infos
            except AttributeError:
                ii = []
            instruction_infos += ii

            try:
                ri = b._register_infos
            except AttributeError:
                ri = {}
            register_infos.update(ri)

        if "_instruction_infos" in attrs:
            instruction_infos += attrs["_instruction_infos"]

        if "_register_infos" in attrs:
            register_infos.extend(attrs["_register_infos"])

        for item_name, item in attrs.items():
            if isinstance(item, Register):
                register_infos[item_name] = item
                continue
            
            if not inspect.isfunction(item):
                continue

            if isinstance(item, staticmethod) or isinstance(item, classmethod):
                continue

            try:
                ii = item._instruction_info
            except AttributeError:
                continue

            instruction_infos.append(ii)
            
        attrs["_instruction_infos"] = instruction_infos[:]
        attrs["_register_infos"] = register_infos

        new_class = type.__new__(cls, name, bases, attrs, **kwargs)
        
        for reg_name, reg_info in register_infos.items():
            reg_info.contribute(new_class, reg_name)
        
        return new_class
    
class Iss(metaclass = IssMeta):
    """Abstract Instruction Set Architecture.

    Instructions and their encoding are registered through metaclass
    programmation. Once instantiated, an ISS object gets all the
    capabilities from its whole inheritance tree.
    """

    @staticmethod
    def encoding(extractor, value):
        def wrapper(f):
            try:
                ii = f._instruction_info
            except AttributeError:
                ii = InstructionInfo(f)
                f._instruction_info = ii
            ii.encoding_add(extractor, value)
            return f
        return wrapper

    def __init__(self, memory):
        self.registers = RegisterSet(self._register_infos)
        
        self.decoders = {}
        for ii in self._instruction_infos:
            self._instruction_info_add(ii)

        self.memory = memory

    def run(self, max_cycles = None, **registers):
        for k, v in registers.items():
            self.registers[k] = v
        cycle = 0
        while cycle != max_cycles:
            cycle += 1
            opcode = self.memory.load(self.pc, 32)
            self.step(opcode)

    def _instruction_info_add(self, ii):
        t = types.MethodType(ii.target_function, self)

        for decoder, values in ii.encodings.items():
            if decoder not in self.decoders:
                d = {}
                self.decoders[decoder] = d
            else:
                d = self.decoders[decoder]

            for v in values:
                d[v] = t
            
    def step(self, opcode):
        for decoder, entries in self.decoders.items():
            key = decoder(opcode)
            if key is None:
                continue

            try:
                target = entries[key]
            except KeyError:
                continue

            return target(opcode)

        return self.unimplemented(opcode)

    @staticmethod
    def sign_extend(value, bits, to = 32):
        """
        Sign-extend a /bits/ value to /to/ bits. Python values are still
        unsigned.
        """
        value &= (1 << bits) - 1
        if value & (1 << (bits - 1)):
            value |= (1 << to) - (1 << bits)
        return value

    @classmethod
    def imm_decode(cls, opcode, ranges, sign_extend_to = None):
        bcount = 0
        ret = 0
        for lsb, msb in ranges:
            if lsb is None:
                bcount += msb
                continue

            s = msb - lsb + 1
            part = (opcode >> lsb) & ((1 << s) - 1)
            ret |= part << bcount

            bcount += s

        if sign_extend_to is not None:
            ret = cls.sign_extend(ret, bcount, sign_extend_to)
        return ret

    def unimplemented(self, opcode):
        raise UndefinedInstruction(opcode)

    def dump(self):
        self.registers.dump()
