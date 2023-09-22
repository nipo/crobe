import math
from .endian import swib, bitswap8
import sys
from functools import cache
from crobe.util.bytes_ops import not_

def crc(data, state, crc_poly, pop_lsb = True, push_lsb = True, inv_state = False):
    assert crc_poly is not None
    assert state is not None
    w = int(math.log2(crc_poly))
    calc = Crc(poly = crc_poly, init = state,
               pop_lsb = pop_lsb, order0_at_lsb = push_lsb,
               complement_input = False, complement_state = inv_state,
               spill_bitswap = False, spill_byte_order = "little")
    return calc.update(state, data)

class Crc:
    def __init__(self, *, poly, init,
                 pop_lsb, order0_at_lsb,
                 complement_input, complement_state,
                 spill_bitswap, spill_byte_order):
        """
        :param int poly: Polynomial as a binary number
        :param int init: Initial value as a binary number
        :param bool pop_lsb: Whether multi-bit values are inserted from MSB or LSB
        :param bool order0_at_lsb: Whether polynom low order is at LSB of poly, init and state
        :param bool complement_input: Whether data bits are to be negated before insertion
        :param bool complement_state: Whether state should be negated before and after any insertion
        :param bool spill_bitswap: Whether result value is bitswapped from state
        :param string spill_byte_order: Byte-order when CRC is multi-byte

        All bits and bytes are numbered from the least
        significant. Significance, even if it has no meaning in GF2,
        is the one from two-complement representation of numbers in Python.
        """
        assert poly & 1, "Even poly is useless"

        self.width = int(math.log2(poly))
        self.byte_width = (self.width + 7) // 8
        self.wbit = 1 << self.width
        self.mask = self.wbit - 1
        self.init = init & self.mask
        self.poly = poly & (self.mask | self.wbit)
        self.lpoly = self.poly & self.mask
        self.rpoly = self.poly >> 1
        if order0_at_lsb:
            self.msb = 1 << (self.width-1)
            self.unit = 1
            self.two = 2
        else:
            self.unit = 1 << (self.width-1)
            self.two = 1 << (self.width-2)
            self.msb = 1

        self.pop_lsb = pop_lsb
        self.order0_at_lsb = order0_at_lsb
        self.complement_input = complement_input
        self.complement_state = complement_state
        self.spill_bitswap = spill_bitswap
        self.spill_byte_order = spill_byte_order

    @property
    @cache
    def check_state(self):
        return self.update(self.init, self.as_bytes(self.init))

    @property
    @cache
    def check_value_int(self):
        return self.as_int(self.check_state)

    @cache
    def reciprocal(self):
        return self.variant(poly = swib(self.poly, self.width+1),
                            init = swib(self.init, self.width),
                            order0_at_lsb = not self.order0_at_lsb,
                            )

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
        if self.order0_at_lsb:
            state = (state << 1) ^ (bit << self.width)
            if state & self.wbit:
                state ^= self.poly
            assert not (state & ~self.mask)
            return state
        else:
            state = state ^ bit
            if state & 1:
                state ^= self.poly
            return state >> 1

    def _backward(self, state, bit = 0):
        if self.order0_at_lsb:
            if state & 1:
                state ^= self.poly
            state ^= bit << self.width
            return state >> 1
        else:
            state <<= 1
            if state & self.wbit:
                state ^= self.poly
            return state ^ bit

    def _forward_bytes(self, state, data):
        for b in self.bytes_iterate(data, self.pop_lsb):
            state = self._forward(state, b)
        return state

    def _backward_bytes(self, state, data):
        for b in self.bytes_iterate(reversed(data), not self.pop_lsb):
            state = self._backward(state, b)
        return state

    def _forward_many(self, state, step_count):
        return self._gfmul(state, self._gfexp(self.two, step_count))

    def _backward_many(self, state, step_count):
        for _ in range(step_count):
            state = self._backward(state, 0)
        return state

    def _gfmul(self, a, b):
        r = 0
        for bit in self.bits_iterate(b, self.width, self.order0_at_lsb):
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
        return self._gfmul(self.lpoly, self._gfexp(2, bit_no))

    def update(self, state, data):
        """
        Forward calculation over data.
        """
        if self.complement_state:
            state = self.mask ^ state

        if self.complement_input:
            data = not_(data)
        state = self._forward_bytes(state, data)

        if self.complement_state:
            state = self.mask ^ state

        return state

    def unupdate(self, state, data):
        """
        Reverse the calculation by data.
        """
        if self.complement_state:
            state = self.mask ^ state

        if self.complement_input:
            data = not_(data)
        state = self._backward_bytes(state, data)

        if self.complement_state:
            state = self.mask ^ state

        return state

    def update_seek(self, state, bit_count):
        """
        Forward seek as if a long bit string of zeros had been input as a
        payload.
        """
        if self.complement_state:
            state = self.mask ^ state

        if self.complement_input:
            for _ in range(bit_count):
                state = self._forward(state, 1)
        else:
            state = self._forward_many(state, bit_count)

        if self.complement_state:
            state = self.mask ^ state

        return state

    def as_int(self, state):
        """
        Spill state integer as an integer
        """
        if self.spill_bitswap:
            return swib(state, self.width)
        return state

    def as_bytes(self, state):
        """
        Spill state integer as a byte string
        """
        val = self.as_int(state)
        return val.to_bytes((self.width + 7) // 8, self.spill_byte_order)

    def __str__(self):
        return f"<Crc poly {self.poly:x}/{self.width} p{'ml'[self.pop_lsb]} 0{'ml'[self.order0_at_lsb]} s{'^-'[self.complement_state]} i{'^-'[self.complement_input]}{' swap' if self.spill_bitswap else ''} {self.spill_byte_order}>"

    def data_mod_state_delta_compute(self, data_offset, data_diff, patch_offset):
        """
        For an opaque payload where data at data_offset has beed changed
        by data_diff (xor of old and new payloads), calculate CRC state delta
        when at offset patch_offset.

        :param int data_offset: Byte offset of changed data bytes in payload
        :param bytes data_diff: Byte string of delta between old and new data
        :param int patch_offset: Byte offset of zone where to calculate state delta
        :returns int: State delta at patch_offset
        """
        data_diff_contribution = self._forward_bytes(0, data_diff)
        offset_to_patch = patch_offset - (data_offset + len(data_diff))

        if offset_to_patch > 0:
            crc_delta = self._forward_many(data_diff_contribution, offset_to_patch * 8)
        else:
            crc_delta = self._backward_many(data_diff_contribution, -offset_to_patch * 8)

        return crc_delta

    def data_mod_data_delta_compute(self, data_offset, data_diff, patch_offset):
        """
        For an opaque payload where data at data_offset has beed changed
        by data_diff, calculate patch to apply to bytes at patch_offset
        to get the same CRC.

        :param int data_offset: Byte offset of changed data bytes in payload
        :param bytes data_diff: Byte string of delta between old and new data
        :param int patch_offset: Byte offset of zone where to fix data
        :returns bytes: Byte string to XOR to data at patch_offset
        """
        crc_delta = self.data_mod_state_delta_compute(data_offset, data_diff, patch_offset)

        if self.order0_at_lsb:
            crc_delta = swib(crc_delta, self.width)
        if self.pop_lsb:
            return crc_delta.to_bytes(self.byte_width, "little")
        else:
            crc_delta = swib(crc_delta, self.width)
            return crc_delta.to_bytes(self.byte_width, "big")

    def data_mod_crc_delta_compute(self, data_offset, data_diff, total_size):
        """
        For an opaque payload or total_size bytes where data at
        data_offset has beed changed by data_diff, calculate patch
        to apply to spilled CRC bytes to have valid payload.

        :param int data_offset: Byte offset of changed data bytes in payload
        :param bytes data_diff: Byte string of delta between old and new data
        :returns bytes: Byte string to XOR to CRC bytes as spilled by algorithm
        """
        crc_delta = self.data_mod_state_delta_compute(data_offset, data_diff, total_size)
        return self.as_bytes(crc_delta)

    def __repr__(self, **kwargs):
        args = [
            ("poly", hex(self.poly)),
            ("init", hex(self.init)),
            ("pop_lsb", str(self.pop_lsb)),
            ("order0_at_lsb", str(self.order0_at_lsb)),
            ("complement_input", str(self.complement_input)),
            ("complement_state", str(self.complement_state)),
            ("spill_bitswap", str(self.spill_bitswap)),
            ("spill_byte_order", repr(self.spill_byte_order)),
        ]
        return "Crc(" + ", ".join(f"{k} = {v}" for (k, v) in args) + ")"

    def __eq__(self, other):
        return True \
            and self.poly == other.poly \
            and self.init == other.init \
            and self.pop_lsb == other.pop_lsb \
            and self.order0_at_lsb == other.order0_at_lsb \
            and self.complement_input == other.complement_input \
            and self.complement_state == other.complement_state \
            and self.spill_bitswap == other.spill_bitswap \
            and self.spill_byte_order == other.spill_byte_order

    def __hash__(self):
        return 0 \
            ^ hash(self.poly) \
            ^ hash(self.init) \
            ^ hash(self.pop_lsb) \
            ^ hash(self.order0_at_lsb) \
            ^ hash(self.complement_input) \
            ^ hash(self.complement_state) \
            ^ hash(self.spill_bitswap) \
            ^ hash(self.spill_byte_order)

    def variant(self, **kwargs):
        """
        Return a variant of current algorithm with only some parameters changed.
        Accepted parameters are all those from constructor.
        """
        defaults = dict(
            poly = self.poly,
            init = self.init,
            pop_lsb = self.pop_lsb,
            order0_at_lsb = self.order0_at_lsb,
            complement_input = self.complement_input,
            complement_state = self.complement_state,
            spill_bitswap = self.spill_bitswap,
            spill_byte_order = self.spill_byte_order,
            )
        defaults.update(kwargs)
        return self.__class__(**defaults)


    def __call__(self, init = None):
        """
        Return a new CrcState object with passed initial value (or
        algorithm's default)
        """
        return State(self, init)

    def calc(self, data, init = None):
        """
        Calculate CRC for a given dataset. This returns the state as a
        final integer. (i.e. with a bit swap if needed)
        """
        if init is None:
            init = self.init
        return self.as_int(self.update(init, data))

    def calc_bytes(self, data, init = None):
        """
        Calculate CRC for a given dataset. This returns the state as a
        final byte string.
        """
        if init is None:
            init = self.init
        return self.as_bytes(self.update(init, data))

    def is_valid(self, data, init = None):
        """
        Checks whether payload (including appended CRC) in data is valid
        for given init value (or algorithm's default).
        """
        if init is None:
            init = self.init
        return self.update(init, data) == self.check_state

    def append_to(self, data, init = None):
        """
        Append correctly formatted CRC to data and return the complete payload.
        """
        return data + self.calc_bytes(data, init)

    def crc_is(self, data, crc, init = None):
        """
        Checks whether the CRC matches the one passed as spilled bytes.
        """
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
        e = "state" if not self.order0_at_lsb else f"(state >> {self.width - 1})"

        print(f"            uint8_t feedback = ({e} ^ {v}) & 1;", file = file)

        shd = ">>" if not self.order0_at_lsb else "<<"

        print(f"            state {shd}= 1;", file = file)
        print("            if (feedback)", file = file)
        print(f"                state ^= {self.lpoly:#x};", file = file)

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


Crc.ethernet_fcs = Crc(
    poly = 0x104c11db7,
    init = 0x0,
    pop_lsb = True, order0_at_lsb = True,
    complement_input = False, complement_state = True,
    spill_bitswap = True,
    spill_byte_order = 'little')

Crc.zlib = Crc.ethernet_fcs.reciprocal().variant(
    spill_bitswap = False,
    spill_byte_order = 'big')

Crc.bluetooth_crc24 = Crc(
    poly = 0x100065b,
    init = 0x55555,
    pop_lsb = True,
    order0_at_lsb = True,
    complement_input = False,
    complement_state = False,
    spill_bitswap = True,
    spill_byte_order = "little")

Crc.hdlc = Crc(
    poly = 0x10811,
    init = 0,
    pop_lsb = True,
    order0_at_lsb = False,
    complement_input = False,
    complement_state = True,
    spill_bitswap = False,
    spill_byte_order = "little")

Crc.iso14443a = Crc.hdlc.variant(
    init = 0x6363,
    complement_state = False)

Crc.iso14443b = Crc.hdlc

Crc.one_wire = Crc(
    poly = 0x119,
    init = 0,
    pop_lsb = True,
    order0_at_lsb = False,
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
