import math
from .endian import bitswap8, swib_u24

def _pop(byte, pop_lsb = True):
    if pop_lsb:
        return byte >> 1, byte & 1
    else:
        return (byte << 1) & 0xff, byte >> 7

def _push(state, bit, poly, w, push_lsb):
    if push_lsb:
        out = state >> (w - 1)
        state <<= 1
        state &= (1 << w) - 1
        if out ^ bit:
            return state ^ poly
        return state
    else:
        out = state & 1
        state >>= 1
        if out ^ bit:
            return state ^ poly
        return state

def crc(data, state, crc_poly, pop_lsb = True, push_lsb = True, inv_state = False):
    assert crc_poly is not None
    w = int(math.log2(crc_poly))
    mask = ((1 << w) - 1)
    poly = crc_poly & mask

    state &= mask
    if inv_state:
        state = state ^ mask
    for b in data:
        for i in range(8):
            b, bit = _pop(b, pop_lsb)
            state = _push(state, bit, poly, w, push_lsb)
    if inv_state:
        state = state ^ mask
    return state

# ZLib flavored
def crc32(data, state = 0):
    return crc(data, state, 0x1edb88320, pop_lsb = True, push_lsb = False, inv_state = True)

if __name__ == "__main__":
    import zlib

    def ble_crc_orig(data, crc):
        crc_poly = 0x100065b
        from crobe.util.endian import bitswap8
        crc = int.from_bytes(bitswap8(crc.to_bytes(3, "big")), "little")

        for b in data:
            for i in range(8):
                crc <<= 1
                crc ^= ((1 & (b >> i)) << 24)
                if crc & 0x1000000:
                    crc ^= crc_poly
        from crobe.util.endian import bitswap8
        return int.from_bytes(bitswap8(crc.to_bytes(3, "big")), "little")

    assert crc32(b"0123456789", 0xdeadbeef) == zlib.crc32(b"0123456789", 0xdeadbeef)
    assert crc32(b"0123456789") == zlib.crc32(b"0123456789")
