from crobe.util.crc import Crc
import unittest

# Compute CRC of message m of size l bits
def crc(m, l, init = 0):
    crc = init
    for i in range(l - 1, -1, -1):
        carry = (crc >> 15) ^ (m >> i);
        crc = (crc << 1) & 0xffff;
        if carry & 1:
            crc = crc ^ 0x8005
    return crc

# Multiplication in the Galois Field
# This computes a * b
def gfmul(a, b):
    r = 0
    for i in range(15, -1, -1):
        r = r << 1
        if (b >> i) & 1:
            r = r ^ a
        if r & 0x10000:
            r = r ^ 0x18005
    return r

# Alternate multiplication algorithm
def gfmul_(a, b):
    r = 0
    while b:
        if b & 1:
            r = r ^ a
        b = b >> 1
        a = a << 1
        if a & 0x10000:
            a = a ^ 0x18005
    return r

# Exponentiation in the Galois Field.
# This computes x**n.
def gfexp(x, n):
    r = 1
    while n != 0:
        if n & 1:
            r = gfmul(r, x)
        x = gfmul(x, x)
        n = n >> 1
    return r

# Linear Feedback Shift Register.
# Start with value x and shift n times.
# This is a slow way to compute x * 2**n in the Galois Field.
def lfsr(x, n):
    for i in range(0, n):
        carry = (x >> 15) & 1
        x = x << 1
        if carry:
            x = x ^ 0x18005
    return x

# Compute CRC contribution of a single bit set.
# Last bit of data has position 0.
def crc_of_bit(pos):
    return gfmul(0x8005, gfexp(2, pos))
    #return lfsr(0x8005, pos)

# Compute CRC contribution of initial value.
def crc_init(init, len):
    return gfmul(init, gfexp(2, len))
    #return lfsr(init, len)

matching_alg = Crc(width = 16,
          poly = 0x8005, init = 0,
          pop_lsb = False, insert_msb = False,
          complement_input = False, complement_state = False,
          spill_bitswap = False, spill_byte_order = "little")

all_algs = [
    matching_alg,
    Crc.zlib,
    Crc.ethernet_fcs,
    Crc.bluetooth_crc24,
]

class SelfTest(unittest.TestCase):
    def test_ops(self):

        self.assertEqual(gfmul(0x1234, 0xabcd), gfmul(0xabcd, 0x1234))

        self.assertEqual(gfmul_(0x1234, 0xabcd), gfmul(0x1234, 0xabcd))
        self.assertEqual(gfmul_(0xabcd, 0x1234), gfmul(0x1234, 0xabcd))

        self.assertEqual(crc_of_bit(108), lfsr(0x8005, 108))

    def test_self(self):
        self.assertEqual(crc_init(0xffff, 17), lfsr(0xffff, 17))

        # LFSR fast forward
        a = 0x1234
        b = 42

        self.assertEqual(gfmul(a, gfexp(2, b)), lfsr(a, b))


        # Adjust CRC for a single data bit change
        self.assertEqual(crc(0x48000, 20) ^ crc_of_bit(15), crc(0x40000, 20))


        # CRC with non zero init value
        self.assertEqual(crc_init(0xffff, 8) ^ crc(0x5a, 8, 0), crc(0x5a, 8, 0xffff))

        # CRC lookup table for byte wide processing of data

        lut = list(map(lambda x: gfmul(0x8005, x), range(0, 256)))

        # Merging CRCs

        a = 0x1234
        b = 0xabcd

        # CRC of a single 32 bits message concat(b, a)
        c = crc((b << 16) | a, 32)

        # CRC of split messages
        q1 = gfexp(2, 16)
        q2 = gfexp(2, 32)

        self.assertEqual(gfmul(a, q1), crc(a, 16))

        self.assertEqual(c, gfmul(a, q1) ^ gfmul(b, q2))

        # An other way to merge CRCs of split messages
        self.assertEqual(c, gfmul(q1, crc(b, 16)) ^ crc(a, 16))

        # Merging of arbitrary message size

        l = 8
        n = 20

        a = 0xe0
        b = 0x48000
        c = 0x48000e0

        self.assertEqual(gfmul(gfexp(2, l), crc(b, n)) ^ crc(a, l), crc(c, n+l))

        crcd = crc(0x123456, 24)
        crci = gfmul(0xffff, gfexp(2, 24)) ^ crcd

        self.assertEqual(hex(crc(0x123456, 24, 0xffff)), hex(crci))

        crci = gfmul(crc(3, 2, 0xffff), gfexp(2, 24)) ^ crcd

        self.assertEqual(hex(crc(0x3123456, 26, 0xffff)), hex(crci))

    def test_alg(self):
        blob = b"deadbeef"
        blob_int = int.from_bytes(blob, "big")
        blob_int_len = len(blob) * 8
        self.assertEqual(matching_alg.calc(blob), crc(blob_int, blob_int_len))

        self.assertEqual(matching_alg._gfmul(0x1234, 0xdead), gfmul(0x1234, 0xdead))
        self.assertEqual(matching_alg._gfexp(0x1234, 20), gfexp(0x1234, 20))

        state = 0
        for i in range(blob_int_len):
            if (blob_int >> i) & 1:
                state ^= matching_alg._contribution_at_bit(i)
        self.assertEqual(state, matching_alg.calc(blob))
        
class GfOps(unittest.TestCase):
    def test_mul(self):
        for alg in all_algs:
            self.assertEqual(alg._gfmul(0xdead, 0xbeef), alg._gfmul(0xbeef, 0xdead))

    def test_square(self):
        value = 0xdead
        for alg in all_algs:
            self.assertEqual(alg._gfmul(value, value), alg._gfexp(value, 2))

    def test_exp(self):
        value = 0xdead
        exp = 47
        for alg in all_algs:
            state = value
            for i in range(exp - 1):
                state = alg._gfmul(state, value)

            self.assertEqual(state, alg._gfexp(value, exp))
        
class SeekTests(unittest.TestCase):
    def test_seek(self):
        bit_count = 87 * 8

        for alg in all_algs:
            data = b"deadbeef"
            partial = alg.update(alg.init, data)
            final_base = alg.update(partial, b"\x00" * (bit_count // 8))
            final_seek = alg.update_seek(partial, bit_count)

            self.assertEqual(final_base, final_seek, msg = f"Using {alg}")

    def test_backward0(self):
        for alg in all_algs:
            init = alg.update(alg.init, b"deadbeef")

            seeked = init
            seeked = alg._backward(seeked)
            seeked = alg._forward(seeked)

            self.assertEqual(init, seeked)

    def test_backward1(self):
        for alg in all_algs:
            init = alg.update(alg.init, b"deadbeef")

            seeked = init
            seeked = alg._backward(seeked, 1)
            seeked = alg._forward(seeked, 1)

            self.assertEqual(init, seeked)

    def test_backward_fw_many(self):
        bit_count = 1

        for alg in all_algs:
            init = alg.update(alg.init, b"deadbeef")

            seeked = init
            for i in range(bit_count):
                seeked = alg._backward(seeked)
            seeked = alg._forward_many(seeked, bit_count)

            self.assertEqual(init, seeked)

    def test_backward_seek(self):
        bit_count = 57

        for alg in all_algs:
            init = alg.update(alg.init, b"deadbeef")

            seeks = [init]
            for i in range(bit_count):
                seeks.append(alg._forward(seeks[-1]))

            for i in range(len(seeks)-1, 0, -1):
                state = seeks[i]
                pre_image = seeks[i-1]
                pre_calc = alg._backward(state)
                self.assertEqual(pre_calc, pre_image, f"Pre-image of {state:x}, expect {pre_image:x}, had {pre_calc:x} error {pre_image ^ pre_calc:x}, alg = {alg}")

    def test_backward_update(self):
        part1 = b"Some long message"
        part2 = b", with more data"

        for alg in all_algs:
            cpart1 = alg.update(alg.init, part1)
            cpart12 = alg.update(cpart1, part2)
            cpart12m2 = alg.unupdate(cpart12, part2) 

            self.assertEqual(cpart1, cpart12m2)

class PatchTests(unittest.TestCase):
    def test_patch(self):
        original_data = bytes.fromhex("10f9c510cecccb70a9dee996e074e2cfbb7120a590b568c808c106f3636b7015")
        patch_offset = 8
        patch_data = bytes.fromhex("c334993b")

        for alg in all_algs:
            data_crc = alg.update(alg.init, original_data)

            patched_data = original_data[:patch_offset] + patch_data + original_data[patch_offset+len(patch_data):]
            patched_data_crc = alg.update(alg.init, patched_data)

            self.assertNotEqual(data_crc, patched_data_crc)

            
            patch_delta = bytes((x^y) for (x, y) in zip(patch_data, original_data[patch_offset:]))
            crc_patch = alg._forward_bytes(0, patch_delta)
            crc_patch = alg._forward_many(crc_patch, 8 * (len(original_data) - len(patch_data) - patch_offset))
            fast_patched_data_crc = data_crc ^ crc_patch
            self.assertNotEqual(data_crc, fast_patched_data_crc)
