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
    db = {}

    @classmethod
    def register(cls, name, obj):
        cls.db[name] = obj

    @classmethod
    def register_info(cls, name, info):
        cls.db[name] = cls.from_info(info)
    
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

        self.order = int(math.log2(poly))
        self.byte_width = (self.order + 7) // 8
        self.wbit = 1 << self.order
        self.mask = self.wbit - 1
        self.init = init & self.mask
        self.poly = poly & (self.mask | self.wbit)
        self.lpoly = self.poly & self.mask
        self.rpoly = self.poly >> 1
        if order0_at_lsb:
            self.unit = 1
            self.two = 2
            self.msb = 1 << (self.order-1)
        else:
            self.unit = 1 << (self.order-1)
            self.two = 1 << (self.order-2)
            self.msb = 1

        self.pop_lsb = pop_lsb
        self.order0_at_lsb = order0_at_lsb
        self.complement_input = complement_input
        self.complement_state = complement_state
        self.state_comp = self.mask if self.complement_state else 0
        self.spill_bitswap = spill_bitswap
        self.spill_byte_order = spill_byte_order

    @property
    @cache
    def check_state(self):
        return self.update(self.init, self.as_bytes(self.init))

    @property
    def is_prime(self):
        p = self.poly
        if not self.order0_at_lsb:
            p = swib(self.poly, self.order+1)
        return p in _all_primes
    
    @property
    @cache
    def check_value_int(self):
        return self.as_int(self.check_state)

    @cache
    def order_swapped(self):
        """
        Return same CRC algorithm but with exponent 0 at LSB of state /
        polynom / init values.
        """
        return self.variant(poly = swib(self.poly, self.order+1),
                            init = swib(self.init, self.order),
                            order0_at_lsb = not self.order0_at_lsb,
                            spill_bitswap = not self.spill_bitswap,
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

    @property
    def poly_exponents(self):
        r = []
        for i in range(self.order + 1):
            if self.poly & (1 << i):
                if self.order0_at_lsb:
                    r.append(i)
                else:
                    r.append(self.order - i)
        r.sort(reverse = True)
        return r

    @property
    def init_exponents(self):
        r = []
        for i in range(self.order + 1):
            if self.init & (1 << i):
                if self.order0_at_lsb:
                    r.append(i)
                else:
                    r.append(self.order - i)
        r.sort(reverse = True)
        return r

    def _forward(self, state, bit = 0):
        if self.order0_at_lsb:
            state = (state << 1) ^ (bit << self.order)
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
            state ^= bit << self.order
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
        for bit in self.bits_iterate(b, self.order, self.order0_at_lsb):
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
        state = self.state_comp ^ state

        if self.complement_input:
            data = not_(data)
        state = self._forward_bytes(state, data)

        return self.state_comp ^ state

    def unupdate(self, state, data):
        """
        Reverse the calculation by data.
        """
        state = self.state_comp ^ state

        if self.complement_input:
            data = not_(data)
        state = self._backward_bytes(state, data)

        return self.state_comp ^ state

    def update_seek(self, state, bit_count):
        """
        Forward seek as if a long bit string of zeros had been input as a
        payload.
        """
        state = self.state_comp ^ state

        if self.complement_input:
            for _ in range(bit_count):
                state = self._forward(state, 1)
        else:
            state = self._forward_many(state, bit_count)

        return self.state_comp ^ state

    def as_int(self, state):
        """
        Spill state integer as an integer
        """
        if self.spill_bitswap:
            return swib(state, self.order)
        return state

    def as_bytes(self, state):
        """
        Spill state integer as a byte string
        """
        val = self.as_int(state)
        return val.to_bytes(self.byte_width, self.spill_byte_order)

    def from_bytes(self, crc):
        """
        Recover state from CRC bytes
        """
        val = int.from_bytes(crc, self.spill_byte_order)
        return self.from_int(val)

    def from_int(self, value):
        """
        Recovert state from spilled integer
        """
        if self.spill_bitswap:
            return swib(value, self.order)
        return value

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
            crc_delta = swib(crc_delta, self.order)
        if self.pop_lsb:
            return crc_delta.to_bytes(self.byte_width, "little")
        else:
            crc_delta = swib(crc_delta, self.order)
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

    @classmethod
    def from_name(cls, name):
        try:
            return cls.db[name]
        except:
            raise ValueError(name)

    @classmethod
    def from_desc_string(cls, s):
        try:
            return cls.from_name(s)
        except ValueError:
            pass

        try:
            return cls.from_reveng(s)
        except ValueError:
            pass

        try:
            return cls.from_info(s)
        except ValueError:
            pass

        raise ValueError(s)
        
    @classmethod
    def from_info(cls, info):
        import re
        m = re.match(r"^(?P<poly>0x[0-9a-f]+)(?P<init>:0x[0-9a-f]+)?(?P<pop_lsb>l)?(?P<order0_at_lsb>z)?(?P<complement_state>s)?(?P<complement_input>i)?(?P<spill_bitswap>x)?(?P<spill_byte_order>[lh])$", info, re.I)
        if not m:
            raise ValueError(info)

        poly = int(m.group("poly"), 16)
        init = int(m.group("init")[1:], 16) if m.group("init") else 0
        pop_lsb = bool(m.group("pop_lsb"))
        order0_at_lsb = bool(m.group("order0_at_lsb"))
        complement_state = bool(m.group("complement_state"))
        complement_input = bool(m.group("complement_input"))
        spill_bitswap = bool(m.group("spill_bitswap"))
        spill_byte_order = "big" if m.group("spill_byte_order") == 'h' else "little"

        return cls(poly = poly, init = init,
                   pop_lsb = pop_lsb, order0_at_lsb = order0_at_lsb,
                   complement_state = complement_state,
                   complement_input = complement_input,
                   spill_bitswap = spill_bitswap,
                   spill_byte_order = spill_byte_order)

    @property
    def info_string(self):
        return f"{self.poly:#x}{':'+hex(self.init) if self.init else ''}{'l' if self.pop_lsb else ''}{'z' if self.order0_at_lsb else ''}{'s' if self.complement_state else ''}{'i' if self.complement_input else ''}{'x' if self.spill_bitswap else ''}{'lh'[self.spill_byte_order == 'big']}"

    @property
    def known_name(self):
        for k, v in sorted(self.algorithms(), reverse = True):
            if v == self:
                return k
        raise ValueError("No known name")

    @property
    def known_names(self):
        r = []
        for k, v in sorted(self.algorithms(), reverse = True):
            if v == self:
                r.append(k)
        return r
    
    def __str__(self):
        try:
            return self.known_name
        except ValueError:
            pass
        return self.info_string

    @classmethod
    def algorithms(cls):
        for k, v in sorted(cls.db.items()):
            if isinstance(v, cls):
                yield k, v

    @property
    def is_trinomial(self):
        return len(self.poly_exponents) <= 3
                
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

    @classmethod
    def from_reveng(cls, reveng_string):
        """
        Return algorithm from reveng definiton
        """
        parameters = dict([x.split("=",1) for x in reveng_string.split()])
        mask = (1 << int(parameters["width"])) - 1
        poly = (1 << int(parameters["width"])) | int(parameters["poly"], 16)
        init = int(parameters["init"], 16)
        check = int(parameters["check"], 16)
        residue = int(parameters["residue"], 16)
        xorout = int(parameters["xorout"], 16)

        if xorout != 0 and xorout != mask:
            raise NotImplementedError("Non-all-equivalent xorout not supported")

        complement_state = bool(xorout)
        
        pop_lsb = parameters["refin"] == "true"
        spill_bitswap = parameters["refout"] == "true"
        name = parameters["name"].strip('"')

        if complement_state:
            init = init ^ mask
        
        r = cls(poly = poly, init = init,
                pop_lsb = pop_lsb, order0_at_lsb = True,
                complement_state = complement_state,
                complement_input = False,
                spill_bitswap = spill_bitswap,
                spill_byte_order = "little")

        r._reveng_check = check
        r._reveng_residue = residue
        r._reveng_name = name
        return r

    @property
    def reveng_string(self):
        fmt = "%%#0%dx" % (2 + (self.order + 3) // 4)
        xorout = self.mask if self.complement_state else 0
        iinit = self.init ^ xorout
        check = self.calc(b"123456789")
        ires = self._forward_many(xorout, self.order)
        if self.pop_lsb:
            ires = swib(ires, self.order)
        reveng_def = [
            ("width", self.order),
            ("poly", fmt % self.lpoly),
            ("init", fmt % iinit),
            ("refin", str(self.pop_lsb).lower()),
            ("refout", str(self.spill_bitswap).lower()),
            ("xorout", fmt % xorout),
            ("check", fmt % check),
            ("residue", fmt % ires),
        ]
        return " ".join(f"{k}={v}" for (k, v) in reveng_def)

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

    def state_error(self, message_with_crc, init = None):
        """
        For a message with CRC appended respecting algorithm spilling
        method, return state difference.
        """
        if init is None:
            init = self.init

        expected_state = self.update(init, message_with_crc[:-self.byte_width])
        loaded_state = self.from_bytes(message_with_crc[-self.byte_width:])

        return expected_state ^ loaded_state

    def bit_contributions(self, crced_message_length):
        """
        Compute map from bit position to contribution in final state up to
        crced_message_length bytes. This returns a 8 *
        crced_message_length element map.
        """
        r = {}

        state = self.unit
        bit_ex = 0 if self.pop_lsb else 7
        for i in range(crced_message_length * 8 - 1, -1, -1):
            r[i ^ bit_ex] = state
            state = self._forward(state, 0)

        return r

Crc.register("ethernet_fcs", Crc(
    poly = 0x104c11db7,
    init = 0x0,
    pop_lsb = True, order0_at_lsb = True,
    complement_input = False, complement_state = True,
    spill_bitswap = True,
    spill_byte_order = 'little'))

Crc.register("zlib", Crc.from_name("ethernet_fcs").order_swapped().variant(
    spill_byte_order = 'big'))

Crc.register("bluetooth_crc24", Crc(
    poly = 0x100065b,
    init = 0x555555,
    pop_lsb = True,
    order0_at_lsb = True,
    complement_input = False,
    complement_state = False,
    spill_bitswap = True,
    spill_byte_order = "little"))

Crc.register("hdlc", Crc(
    poly = 0x10811,
    init = 0,
    pop_lsb = True,
    order0_at_lsb = False,
    complement_input = False,
    complement_state = True,
    spill_bitswap = False,
    spill_byte_order = "little"))

Crc.register("iso14443a", Crc.from_name("hdlc").variant(
    init = 0x6363,
    complement_state = False))

Crc.register("iso14443b", Crc.from_name("hdlc"))

Crc.register("one_wire", Crc(
    poly = 0x119,
    init = 0,
    pop_lsb = True,
    order0_at_lsb = False,
    complement_input = False,
    complement_state = False,
    spill_bitswap = False,
    spill_byte_order = "little"))

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

# From http://web.eecs.utk.edu/~jplank/plank/papers/CS-07-593/primitive-polynomial-table.txt
_all_primes = set([
    0o7,
    0o13,
    0o23,
    0o45, 0o75, 0o67,
    0o103, 0o147, 0o155,
    0o211, 0o217, 0o235, 0o367, 0o277, 0o325, 0o203, 0o313, 0o345,
    0o435, 0o551, 0o747, 0o453, 0o545, 0o537, 0o703, 0o543,
    0o1021, 0o1131, 0o1461, 0o1423, 0o1055, 0o1167, 0o1541,
    0o1333, 0o1605, 0o1751, 0o1743, 0o1617, 0o1553, 0o1157,
    0o2011, 0o2415, 0o3771, 0o2157, 0o3515, 0o2773, 0o2033,
    0o2443, 0o2461, 0o3023, 0o3543, 0o2745, 0o2431, 0o3177,
    0o4005, 0o4445, 0o4215, 0o4055, 0o6015, 0o7413, 0o4143,
    0o4563, 0o4053, 0o5023, 0o5623, 0o4577, 0o6233, 0o6673,
    0o10123, 0o15647, 0o16533, 0o16047, 0o11015, 0o14127,
    0o17673, 0o13565, 0o15341, 0o15053, 0o15621, 0o15321,
    0o11417, 0o13505,
    0o20033, 0o23261, 0o24623, 0o23517, 0o30741, 0o21643,
    0o30171, 0o21277, 0o27777, 0o35051, 0o34723, 0o34047,
    0o32535, 0o31425,
    0o42103, 0o43333, 0o51761, 0o40503, 0o77141, 0o62677,
    0o44103, 0o45145, 0o76303, 0o64457, 0o57231, 0o64167,
    0o60153, 0o55753,
    0o100003, 0o102043, 0o110013, 0o102067, 0o104307, 0o100317,
    0o177775, 0o103451, 0o110075, 0o102061, 0o114725, 0o103251,
    0o100021, 0o100201,
    0o210013, 0o234313, 0o233303, 0o307107, 0o307527, 0o306357,
    0o201735, 0o272201, 0o242413, 0o270155, 0o302157, 0o210205,
    0o305667, 0o236107,
    0o400011, 0o400017, 0o400431, 0o525251, 0o410117, 0o400731,
    0o411335, 0o444257, 0o600013, 0o403555, 0o525327, 0o411077,
    0o400041, 0o400101,
    0o1000201, 0o1000247, 0o1002241, 0o1002441, 0o1100045,
    0o1000407, 0o1003011, 0o1020121, 0o1101005, 0o1000077,
    0o1001361, 0o1001567, 0o1001727, 0o1002777,
    0o2000047, 0o2000641, 0o2001441, 0o2000107, 0o2000077,
    0o2000157, 0o2000175, 0o2000257, 0o2000677, 0o2000737,
    0o2001557, 0o2001637, 0o2005775, 0o2006677,
    0o4000011, 0o4001051, 0o4004515, 0o6000031, 0o4442235,
    0o10000005, 0o10040205, 0o10020045, 0o10040315, 0o10000635,
    0o10103075, 0o10050335, 0o10002135, 0o17000075,
    0o20000003, 0o20001043, 0o2222223, 0o25200127, 0o20401207,
    0o20430607, 0o20070217,
    0o40000041, 0o40404041, 0o40000063, 0o40010061, 0o50000241,
    0o40220151, 0o40006341, 0o40405463, 0o40103271, 0o41224445,
    0o4043561,
    0o100000207, 0o125245661, 0o113763063,
    0o200000011, 0o200000017, 0o204000051, 0o200010031,
    0o200402017, 0o252001251, 0o201014171, 0o204204057,
    0o200005535, 0o200014731,
    0o400000107, 0o430216473, 0o402365755, 0o426225667,
    0o510664323, 0o473167545, 0o411335571,
    0o1000000047, 0o1001007071, 0o1020024171, 0o1102210617,
    0o1250025757, 0o1257242631, 0o1020560103, 0o1112225171,
    0o1035530241,
    0o2000000011, 0o2104210431, 0o2000025051, 0o2020006031,
    0o2002502115, 0o2001601071,
    0o4000000005, 0o4004004005, 0o4000010205, 0o4010000045,
    0o4400000045, 0o4002200115, 0o4001040115, 0o4004204435,
    0o4100060435, 0o4040003075, 0o40040642751,
    0o10040000007, 0o10104264207, 0o10115131333, 0o11362212703,
    0o10343244533,
    0o20000000011, 0o20000000017, 0o20000020411, 0o21042104211,
    0o20010010017, 0o20005000251, 0o20004100071, 0o20202040217,
    0o20000200435, 0o20060140231, 0o21042107357,
    0o40020000007, 0o40460216667, 0o40035532523, 0o42003247143,
    0o41760427607,
    0o100000020001, 0o100020024001, 0o104000420001,
    0o100020224401, 0o111100021111, 0o100000031463,
    0o104020466001, 0o100502430041, 0o100601431001,
    0o201000000007, 0o201472024107, 0o377000007527,
    0o225213433257, 0o227712240037, 0o251132516577,
    0o211636220473, 0o200000140003,
    0o400000000005,
    0o1000000004001,
    0o2000000012005,
    0o4000000000143,
    0o10000000000021,
    0o20000012000005,
    0o200000000000000000047,
    0o400000000000000000000000000151,
])

for name, info in [
    ('CRC-8/AUTOSAR', '0x12fzsl'),
    ('CRC-8/BLUETOOTH', '0x1a7lzxl'),
    ('CRC-8/CDMA2000', '0x19b:0xffzl'),
    ('CRC-8/DARC', '0x139lzxl'),
    ('CRC-8/DVB-S2', '0x1d5zl'),
    ('CRC-8/GSM-A', '0x11dzl'),
    ('CRC-8/GSM-B', '0x149:0xffzsl'),
    ('CRC-8/HITAG', '0x11d:0xffzl'),
    ('CRC-8/I-CODE', '0x11d:0xfdzl'),
    ('CRC-8/LTE', '0x19bzl'),
    ('CRC-8/MAXIM-DOW', '0x131lzxl'),
    ('CRC-8/MIFARE-MAD', '0x11d:0xc7zl'),
    ('CRC-8/NRSC-5', '0x131:0xffzl'),
    ('CRC-8/OPENSAFETY', '0x12fzl'),
    ('CRC-8/ROHC', '0x107:0xfflzxl'),
    ('CRC-8/SAE-J1850', '0x11dzsl'),
    ('CRC-8/SMBUS', '0x107zl'),
    ('CRC-8/TECH-3250', '0x11d:0xfflzxl'),
    ('CRC-8/WCDMA', '0x19blzxl'),
    ('CRC-16/ARC', '0x18005lzxl'),
    ('CRC-16/CDMA2000', '0x1c867:0xffffzl'),
    ('CRC-16/CMS', '0x18005:0xffffzl'),
    ('CRC-16/DDS-110', '0x18005:0x800dzl'),
    ('CRC-16/DECT-X', '0x10589zl'),
    ('CRC-16/DNP', '0x13d65:0xfffflzsxl'),
    ('CRC-16/EN-13757', '0x13d65:0xffffzsl'),
    ('CRC-16/GENIBUS', '0x11021zsl'),
    ('CRC-16/GSM', '0x11021:0xffffzsl'),
    ('CRC-16/IBM-3740', '0x11021:0xffffzl'),
    ('CRC-16/IBM-SDLC', '0x11021lzsxl'),
    ('CRC-16/ISO-IEC-14443-3-A', '0x11021:0xc6c6lzxl'),
    ('CRC-16/KERMIT', '0x11021lzxl'),
    ('CRC-16/LJ1200', '0x16f63zl'),
    ('CRC-16/M17', '0x15935:0xffffzl'),
    ('CRC-16/MAXIM-DOW', '0x18005:0xfffflzsxl'),
    ('CRC-16/MCRF4XX', '0x11021:0xfffflzxl'),
    ('CRC-16/MODBUS', '0x18005:0xfffflzxl'),
    ('CRC-16/NRSC-5', '0x1080b:0xfffflzxl'),
    ('CRC-16/OPENSAFETY-A', '0x15935zl'),
    ('CRC-16/OPENSAFETY-B', '0x1755bzl'),
    ('CRC-16/PROFIBUS', '0x11dcfzsl'),
    ('CRC-16/RIELLO', '0x11021:0xb2aalzxl'),
    ('CRC-16/SPI-FUJITSU', '0x11021:0x1d0fzl'),
    ('CRC-16/T10-DIF', '0x18bb7zl'),
    ('CRC-16/TELEDISK', '0x1a097zl'),
    ('CRC-16/TMS37157', '0x11021:0x89eclzxl'),
    ('CRC-16/UMTS', '0x18005zl'),
    ('CRC-16/USB', '0x18005lzsxl'),
    ('CRC-16/XMODEM', '0x11021zl'),
    ('CRC-24/BLE', '0x100065b:0x555555lzxl'),
    ('CRC-24/FLEXRAY-A', '0x15d6dcb:0xfedcbazl'),
    ('CRC-24/FLEXRAY-B', '0x15d6dcb:0xabcdefzl'),
    ('CRC-24/INTERLAKEN', '0x1328b63zsl'),
    ('CRC-24/LTE-A', '0x1864cfbzl'),
    ('CRC-24/LTE-B', '0x1800063zl'),
    ('CRC-24/OPENPGP', '0x1864cfb:0xb704cezl'),
    ('CRC-24/OS-9', '0x1800063zsl'),
    ('CRC-32/AIXM', '0x1814141abzl'),
    ('CRC-32/AUTOSAR', '0x1f4acfb13lzsxl'),
    ('CRC-32/BASE91-D', '0x1a833982blzsxl'),
    ('CRC-32/BZIP2', '0x104c11db7zsl'),
    ('CRC-32/CD-ROM-EDC', '0x18001801blzxl'),
    ('CRC-32/CKSUM', '0x104c11db7:0xffffffffzsl'),
    ('CRC-32/ISCSI', '0x11edc6f41lzsxl'),
    ('CRC-32/ISO-HDLC', '0x104c11db7lzsxl'),
    ('CRC-32/JAMCRC', '0x104c11db7:0xfffffffflzxl'),
    ('CRC-32/MEF', '0x1741b8cd7:0xfffffffflzxl'),
    ('CRC-32/MPEG-2', '0x104c11db7:0xffffffffzl'),
    ('CRC-32/XFER', '0x1000000afzl'),
    ('CRC-40/GSM', '0x10004820009:0xffffffffffzsl'),
    ('CRC-64/ECMA-182', '0x142f0e1eba9ea3693zl'),
    ('CRC-64/GO-ISO', '0x1000000000000001blzsxl'),
    ('CRC-64/MS', '0x1259c84cba6426349:0xfffffffffffffffflzxl'),
    ('CRC-64/REDIS', '0x1ad93d23594c935a9lzxl'),
    ('CRC-64/WE', '0x142f0e1eba9ea3693zsl'),
    ('CRC-64/XZ', '0x142f0e1eba9ea3693lzsxl'),
        ]:
    Crc.register_info(name, info)
