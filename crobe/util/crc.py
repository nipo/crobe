import math
from .endian import swib
import sys

def crc(data, state, crc_poly, pop_lsb = True, push_lsb = True, inv_state = False):
    assert crc_poly is not None
    assert state is not None
    w = int(math.log2(crc_poly))
    calc = Crc(width = w, poly = crc_poly, init = state,
               pop_lsb = pop_lsb, insert_msb = not push_lsb,
               complement_input = False, complement_state = inv_state,
               spill_bitswap = False, spill_byte_order = "little")
    return calc.update(state, data)

class Crc:
    def __init__(self, *, width, poly, init,
                 pop_lsb, insert_msb,
                 complement_input, complement_state,
                 spill_bitswap, spill_byte_order):
        """
        :param int width: Width of CRC
        :param int poly: Polynomial as a binary number
        :param int init: Initial value as a binary number
        :param bool pop_lsb: Whether multi-bit values are inserted from MSB or LSB
        :param bool insert_msb: Whether new bits are pushed to MSB or LSB of state
        :param bool complement_input: Whether data bits are to be negated before insertion
        :param bool complement_state: Whether state should be negated before and after any insertion
        :param bool spill_bitswap: Whether result value is bitswapped from state
        :param string spill_byte_order: Byte-order when CRC is multi-byte

        All bits and bytes are numbered from the least
        significant. Significance, even if it has no meaning in GF2,
        is the one from two-complement representation of numbers in Python.
        """
        self.width = width
        self.byte_width = (width + 7) // 8
        self.wbit = 1 << width
        self.mask = self.wbit - 1
        self.poly = poly & self.mask
        self.init = init & self.mask
        if insert_msb:
            self.unit = 1 << (width-1)
            self.two = 1 << (width-2)
            self.msb = 1
            self.wpoly = (poly << 1) | 1
            self.rpoly = self.wpoly & self.mask
        else:
            self.msb = 1 << (width-1)
            self.unit = 1
            self.two = 2
            self.wpoly = poly | (1 << width)
            self.rpoly = self.wpoly >> 1

        self.pop_lsb = pop_lsb
        self.insert_msb = insert_msb
        self.complement_input = complement_input
        self.complement_state = complement_state
        self.spill_bitswap = spill_bitswap
        self.spill_byte_order = spill_byte_order

        self.check_state = self.update(self.init, self.as_bytes(self.init))
        self.check_value_int = self.as_int(self.check_state)

    @classmethod
    def bits_iterate(cls, word, width, pop_lsb):
        for i in range(width):
            if pop_lsb:
                yield word & 1
                word >>= 1
            else:
                yield (word >> (width - 1)) & 1
                word <<= 1

    @classmethod
    def bytes_iterate(cls, data, pop_lsb):
        for b in data:
            yield from cls.bits_iterate(b, 8, pop_lsb)
            
    def _forward(self, state, bit = 0):
        if self.insert_msb:
            out = state & 1
            state = state >> 1
        else:
            out = state >> (self.width - 1)
            state = (state << 1) & self.mask

        if out ^ bit:
            return state ^ self.poly
        return state
    
    def _backward(self, state, bit = 0):
        if self.insert_msb:
            out = state >> (self.width - 1)
            state = ((state << 1) & self.mask) ^ bit
        else:
            out = state & 1
            state = (state >> 1) ^ (bit << (self.width - 1))

        if out:
            return state ^ self.rpoly
        return state
    
    def _forward_bytes(self, state, data):
        for b in self.bytes_iterate(data, self.pop_lsb):
            state = self._forward(state, b ^ self.complement_input)
        return state

    def _backward_bytes(self, state, data):
        for b in self.bytes_iterate(data[::-1], not self.pop_lsb):
            state = self._backward(state, b ^ self.complement_input)
        return state

    def _forward_many(self, state, step_count):
        return self._gfmul(state, self._gfexp(self.two, step_count))

    def _backward_many(self, state, step_count):
        for _ in range(step_count):
            state = self._backward(state, 0)
        return state

    def _gfmul(self, a, b):
        r = 0
        for bit in self.bits_iterate(b, self.width, not self.insert_msb):
            if bit:
                r = r ^ a
            a = self._forward(a)
        return r

    def _gfexp(self, x, n):
        r = self.unit
        while n != 0:
            if n & 1:
                r = self._gfmul(r, x)
            x = self._gfmul(x, x)
            n = n >> 1
        return r

    def _contribution_at_bit(self, bit_no):
        return self._gfmul(self.poly, self._gfexp(2, bit_no))
    
    def update(self, state, data):
        if self.complement_state:
            state = self.mask ^ state

        state = self._forward_bytes(state, data)
            
        if self.complement_state:
            state = self.mask ^ state

        return state    

    def unupdate(self, state, data):
        if self.complement_state:
            state = self.mask ^ state

        state = self._backward_bytes(state, data)
            
        if self.complement_state:
            state = self.mask ^ state

        return state    
    
    def update_seek(self, state, bit_count):
        if self.complement_input:
            raise NotImplementedError("Seek unavailable for inverted input")

        if self.complement_state:
            state = self.mask ^ state

        state = self._forward_many(state, bit_count)

        if self.complement_state:
            state = self.mask ^ state

        return state    
    
    def as_int(self, state):
        if self.spill_bitswap:
            return swib(state, self.width)
        return state

    def as_bytes(self, state):
        val = self.as_int(state)
        return val.to_bytes((self.width + 7) // 8, self.spill_byte_order)

    def __str__(self):
        return f"<Crc poly {self.poly:x}/{self.width} p{'ml'[self.pop_lsb]} i{'lm'[self.insert_msb]} s{'^-'[self.complement_state]} i{'^-'[self.complement_input]}{' swap' if self.spill_bitswap else ''} {self.spill_byte_order}>"

    def data_mod_data_delta_compute(self, data_offset, old_data, new_data, patch_offset):
        data_delta = bytes([(a^b) for (a,b) in zip(old_data, new_data)])
        data_delta_contribution = self._forward_bytes(0, data_delta)

        offset_to_patch = patch_offset - (data_offset + len(data_delta))
        
        if offset_to_patch > 0:
            crc_delta = self._forward_many(data_delta_contribution, offset_to_patch * 8)
        else:
            crc_delta = self._backward_many(data_delta_contribution, -offset_to_patch * 8)

        return self.as_bytes(crc_delta)
    
    def __repr__(self, **kwargs):
        args = [
            ("width", str(self.width)),
            ("poly", hex(self.poly)),
            ("init", hex(self.init)),
            ("pop_lsb", str(self.pop_lsb)),
            ("insert_msb", str(self.insert_msb)),
            ("complement_input", str(self.complement_input)),
            ("complement_state", str(self.complement_state)),
            ("spill_bitswap", str(self.spill_bitswap)),
            ("spill_byte_order", repr(self.spill_byte_order)),
        ]
        return "Crc(" + ", ".join(f"{k} = {v}" for (k, v) in args) + ")"

    def __eq__(self, other):
        return True \
            and self.width == other.width \
            and self.poly == other.poly \
            and self.init == other.init \
            and self.pop_lsb == other.pop_lsb \
            and self.insert_msb == other.insert_msb \
            and self.complement_input == other.complement_input \
            and self.complement_state == other.complement_state \
            and self.spill_bitswap == other.spill_bitswap \
            and self.spill_byte_order == other.spill_byte_order

    def __hash__(self):
        return 0 \
            ^ hash(self.width) \
            ^ hash(self.poly) \
            ^ hash(self.init) \
            ^ hash(self.pop_lsb) \
            ^ hash(self.insert_msb) \
            ^ hash(self.complement_input) \
            ^ hash(self.complement_state) \
            ^ hash(self.spill_bitswap) \
            ^ hash(self.spill_byte_order)
    
    def variant(self, **kwargs):
        defaults = dict(
            width = self.width,
            poly = self.poly,
            init = self.init,
            pop_lsb = self.pop_lsb,
            insert_msb = self.insert_msb,
            complement_input = self.complement_input,
            complement_state = self.complement_state,
            spill_bitswap = self.spill_bitswap,
            spill_byte_order = self.spill_byte_order,
            )
        defaults.update(kwargs)
        return self.__class__(**defaults)


    def __call__(self, init = None):
        return State(self, init)

    def calc(self, data, init = None):
        if init is None:
            init = self.init
        return self.as_int(self.update(init, data))

    def calc_bytes(self, data, init = None):
        if init is None:
            init = self.init
        return self.as_bytes(self.update(init, data))

    def is_valid(self, data, init = None):
        if init is None:
            init = self.init
        return self.update(init, data) == self.check_state

    def append_to(self, data, init = None):
        return data + self.calc_bytes(data, init)

    def crc_is(self, data, crc, init = None):
        return self.calc_bytes(data, init) == crc

    def c_bit_spill(self, file = sys.stdout):
        print(f"#define MY_CRC_INIT {self.init:#x}", file = file)
        print(f"uint{self.width}_t my_crc_update(const uint8_t *data, size_t size, uint{self.width}_t state)", file = file)
        print("{", file = file)
        if self.complement_state:
            print("    state = ~state;", file = file)
        print("    for (size_t i = 0; i < size; ++i) {", file = file)
        print("        uint8_t word = data[i];", file = file)
        if self.complement_input:
            print("        word = ~word;", file = file)
        print("        for (size_t bit_index = 0; bit_index < 8; ++bit_index) {", file = file)

        v = "word" if self.pop_lsb else "(word >> 7)"
        e = "state" if self.insert_msb else f"(state >> {self.width - 1})"

        print(f"            uint8_t feedback = ({e} ^ {v}) & 1;", file = file)

        shd = ">>" if self.insert_msb else "<<"

        print(f"            state {shd}= 1;", file = file)
        print("            if (feedback)", file = file)
        print(f"                state ^= {self.poly:#x};", file = file)

        shd = ">>" if self.pop_lsb else "<<"
        
        print(f"            word {shd}= 1;", file = file)
        print("        }", file = file)
        print("    }", file = file)
        if self.complement_state:
            print("    state = ~state;", file = file)
        print("    return state;", file = file)
        print("}", file = file)

    def c_test_spill(self, data = b"012345678", file = sys.stdout):
        print("int main(int argc, char **argv)", file = file)
        print("{", file = file)
        crc = self.update(self.init, data)
        print(f"    const uint8_t data[] = {{{', '.join(hex(x) for x in data)}}};", file = file)
        print(f"    assert(my_crc_update(data, sizeof(data), MY_CRC_INIT) == {crc:#x});", file = file)
        print("    return 0;", file = file)
        print("}", file = file)

        
Crc.zlib = Crc(
    width = 32,
    poly = 0xedb88320,
    init = 0,
    pop_lsb = True,
    insert_msb = True,
    complement_input = False,
    complement_state = True,
    spill_bitswap = False,
    spill_byte_order = "big")

# In RM0008, ST says they use the ethernet CRC, but their IP takes the
# four bytes in opposite order. Moreover, they have no pre/post
# complementation of state, so they initialize with 0xffffffff, but
# forget to tell output should be negated.
Crc.stm32 = Crc(
    width = 32,
    poly = 0x04c11db7,
    init = 0xffffffff,
    pop_lsb = False,
    insert_msb = False,
    complement_input = False,
    complement_state = False,
    spill_bitswap = False,
    spill_byte_order = "big")

Crc.ethernet_fcs = Crc(
    width = 32,
    poly = 0xedb88320,
    init = 0,
    pop_lsb = True,
    insert_msb = True,
    complement_input = False,
    complement_state = True,
    spill_bitswap = False,
    spill_byte_order = "little")

Crc.bluetooth_crc24 = Crc(
    width = 24,
    poly = 0x00065b,
    init = 0x55555,
    pop_lsb = True,
    insert_msb = False,
    complement_input = False,
    complement_state = False,
    spill_bitswap = True,
    spill_byte_order = "little")

Crc.iso14443a = Crc(
    width = 16,
    poly = 0x8408,
    init = 0x6363,
    pop_lsb = True,
    insert_msb = True,
    complement_input = False,
    complement_state = False,
    spill_bitswap = False,
    spill_byte_order = "little")

Crc.iso14443b = Crc(
    width = 16,
    poly = 0x8408,
    init = 0,
    pop_lsb = True,
    insert_msb = True,
    complement_input = False,
    complement_state = True,
    spill_bitswap = False,
    spill_byte_order = "little")

Crc.hdlc = Crc.iso14443b

Crc.one_wire = Crc(
    width = 8,
    poly = 0x8c,
    init = 0,
    pop_lsb = True,
    insert_msb = True,
    complement_input = False,
    complement_state = False,
    spill_bitswap = False,
    spill_byte_order = "little")

class State:
    def __init__(self, backend, init = None):
        self.backend = backend
        if init is None:
            init = backend.init
        self.state = init

    def __call__(self, data):
        self.update(data)
        return int(self)

    def update(self, data):
        self.state = self.backend.update(self.state, data)

    def __int__(self):
        return self.backend.as_int(self.state)

    def __bytes__(self):
        return self.backend.as_bytes(self.state)

    def is_valid(self):
        return self.state == self.backend.check_state
