"""STAPL Advanced Compression Algorithm (ACA) decompressor.

Implements the ACA format defined in JESD71 Section 6.6.
ACA encodes Boolean array data as base-64 text, which decodes to a
compressed binary bitstream containing literal and repeated data blocks.
"""

# Base-64 character to 6-bit value mapping (Table 2)
_CHAR_TO_VAL = {}
for _i in range(10):
    _CHAR_TO_VAL[ord('0') + _i] = _i
for _i in range(26):
    _CHAR_TO_VAL[ord('A') + _i] = 10 + _i
for _i in range(26):
    _CHAR_TO_VAL[ord('a') + _i] = 36 + _i
_CHAR_TO_VAL[ord('_')] = 62
_CHAR_TO_VAL[ord('@')] = 63


def _text_to_bits(text: str) -> bytearray:
    """Convert ACA base-64 text to a compressed binary array.

    Each character maps to a 6-bit value. Four 6-bit values pack into
    three bytes: first value in lower 6 bits of byte 0, second value
    in upper 2 bits of byte 0 and lower 4 bits of byte 1, etc.
    """
    values = []
    for ch in text:
        if ch in (' ', '\t', '\n', '\r'):
            continue
        val = _CHAR_TO_VAL.get(ord(ch))
        if val is None:
            raise ValueError(f"Invalid ACA character: {ch!r}")
        values.append(val)

    # Pack 6-bit values into bytes via a bit accumulator
    result = bytearray()
    bit_acc = 0
    bit_count = 0
    for val in values:
        bit_acc |= val << bit_count
        bit_count += 6
        while bit_count >= 8:
            result.append(bit_acc & 0xFF)
            bit_acc >>= 8
            bit_count -= 8
    if bit_count > 0:
        result.append(bit_acc & 0xFF)

    return result


class _BitReader:
    """Read individual bits from a byte array, LSB first."""

    __slots__ = ('_data', '_byte_pos', '_bit_pos')

    def __init__(self, data: bytearray):
        self._data = data
        self._byte_pos = 0
        self._bit_pos = 0

    def read_bit(self) -> int:
        if self._byte_pos >= len(self._data):
            raise ValueError("Unexpected end of compressed data")
        bit = (self._data[self._byte_pos] >> self._bit_pos) & 1
        self._bit_pos += 1
        if self._bit_pos == 8:
            self._bit_pos = 0
            self._byte_pos += 1
        return bit

    def read_bits(self, count: int) -> int:
        value = 0
        for i in range(count):
            value |= self.read_bit() << i
        return value

    def read_byte(self) -> int:
        return self.read_bits(8)


def _offset_field_width(output_pos: int) -> int:
    """Minimum number of bits to represent output_pos, capped at 13.

    Per spec (Figure 5): the offset field is 1 to 13 bits, and
    1 ≤ Offset ≤ (2^13) - 1. The field width is the minimum number
    of bits required to represent the current position, but never
    exceeds 13 bits.
    """
    if output_pos == 0:
        return 1
    n = min(output_pos.bit_length(), 13)
    return n


def decompress(text: str) -> bytearray:
    """Decompress an ACA-encoded string to raw bytes.

    Args:
        text: ACA compressed text (starting with '@' format symbol,
              which should already be stripped by the caller, or
              included — the leading '@' is part of the base-64
              alphabet with value 63).

    Returns:
        Decompressed byte array.
    """
    compressed = _text_to_bits(text)
    reader = _BitReader(compressed)

    # Read 32-bit little-endian uncompressed data length
    length = 0
    for i in range(4):
        length |= reader.read_byte() << (8 * i)

    output = bytearray()

    while len(output) < length:
        block_type = reader.read_bit()

        if block_type == 0:
            # Literal data block: 3 bytes
            for _ in range(3):
                if len(output) < length:
                    output.append(reader.read_byte())
        else:
            # Repeated data block: offset + length
            n = _offset_field_width(len(output))
            offset = reader.read_bits(n)
            count = reader.read_byte()

            ref_pos = len(output) - offset
            assert ref_pos >= 0, f"Invalid back-reference: offset={offset}, pos={len(output)}"

            remaining = length - len(output)
            copy_count = min(count, remaining)
            for i in range(copy_count):
                output.append(output[ref_pos + i])

    assert len(output) == length, f"Decompressed size mismatch: got {len(output)}, expected {length}"
    return output
