"""STAPL Advanced Compression Algorithm (ACA) decompressor.

Implements the ACA format defined in JESD71 Section 6.6.
ACA encodes Boolean array data as base-64 text, which decodes to a
compressed binary bitstream containing literal and repeated data blocks.
"""

import base64

from ..util.endian import swib, bitswap8
from ..bitstring import BitString


# ACA's 6-bit alphabet (JESD71 Table 2): digits, then upper-case, then
# lower-case, then '_' (62) and '@' (63). Differs from RFC 4648 standard
# base64 (upper, lower, digits, +/) in alphabet ordering AND in bit
# packing: ACA packs 6-bit values LSB-first into the byte stream, std
# base64 packs them MSB-first. Both differences fall out of bit-reversing
# each 6-bit value (during alphabet translation) and bit-reversing each
# output byte (bitswap8) — the result lets stdlib's b64 decoder do the
# heavy lifting.
_ACA_ALPHABET = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "_@"
)
_STD_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "0123456789+/"
)
_ACA_TO_STD = {ord(a): ord(_STD_ALPHABET[swib(i, 6)])
               for i, a in enumerate(_ACA_ALPHABET)}
for _ws in " \t\n\r":
    _ACA_TO_STD[ord(_ws)] = None


def _text_to_bits(text: str) -> bytes:
    """Convert ACA base-64 text to a compressed binary array.

    Each character maps to a 6-bit value, packed LSB-first into bytes.
    Implemented via stdlib base64 by bit-reversing the alphabet mapping
    and bit-reversing each output byte. Inputs whose 6-bit-value count
    isn't a multiple of 4 are zero-padded with 'A' (the std-b64
    zero-value char), preserving ACA's zero-pad-to-byte-boundary
    semantics.
    """
    as_std = text.translate(_ACA_TO_STD)
    as_std += "A" * (-len(as_std) % 4)
    return bitswap8(base64.b64decode(as_std))


def _offset_field_width(output_pos: int) -> int:
    """Minimum number of bits to represent output_pos, capped at 13.

    Per spec (Figure 5): the offset field is 1 to 13 bits, and
    1 ≤ Offset ≤ (2^13) - 1. The field width is the minimum number
    of bits required to represent the current position, but never
    exceeds 13 bits.
    """
    if output_pos == 0:
        return 1
    return min(output_pos.bit_length(), 13)


def decompress(text: str) -> bytes:
    """Decompress an ACA-encoded string to raw bytes.

    Args:
        text: ACA compressed text (starting with '@' format symbol,
              which should already be stripped by the caller, or
              included — the leading '@' is part of the base-64
              alphabet with value 63).

    Returns:
        Decompressed bytes.
    """
    compressed = BitString(_text_to_bits(text))

    length = int(compressed[0:32])
    output = bytearray(length)
    output_pos = 0
    compressed_pos = 32

    while output_pos < length:
        block_type = compressed[compressed_pos]
        compressed_pos += 1

        if block_type == 0:
            # Literal data block: 3 bytes
            n = min(length - output_pos, 3)
            output[output_pos:output_pos + n] = bytes(
                compressed[compressed_pos:compressed_pos + 8 * n])
            compressed_pos += 8 * n
            output_pos += n
        else:
            # Repeated data block: offset + count
            n = _offset_field_width(output_pos)
            offset = int(compressed[compressed_pos:compressed_pos + n])
            compressed_pos += n
            count = int(compressed[compressed_pos:compressed_pos + 8])
            compressed_pos += 8

            ref_pos = output_pos - offset
            assert ref_pos >= 0, f"Invalid back-reference: offset={offset}, pos={output_pos}"

            copy_count = min(count, length - output_pos)
            output[output_pos:output_pos + copy_count] = (
                output[ref_pos:ref_pos + copy_count])
            output_pos += copy_count

    assert output_pos == length, f"Decompressed size mismatch: got {output_pos}, expected {length}"
    return bytes(output)
