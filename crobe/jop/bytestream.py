"""JoP byte stream codec.

Decodes the byte stream Quartus pushes onto the H2T data channel into
high-level shift requests; encodes captured TDO bits back into the
matching T2H byte stream.

The on-chip reference is ``sld_hub_ctrl_core.sv``. Each command byte
encodes a 3-bit opcode in bits [7:5]; the remaining 5 bits carry a
length field (interpreted as ``count - 1``, so the wire encoding
``0..31`` represents ``1..32`` bits).

Commands
--------

============================  =====  ===============  =============================================
Mnemonic                      bits   trailing bytes   meaning
============================  =====  ===============  =============================================
CMD_CONFIG                    000    none             Sub-op in low 2 bits:
                                                      0=retrieve info (returns 1 byte 0x00),
                                                      1=reset TDO-enable FIFO
CMD_WRITE_TDO_ENABLE_FIFO     010    2                Schedule one TDO-capture window of N TCKs.
                                                      Byte 0 low5 = N[4:0]; byte 1 = N[12:5];
                                                      byte 2 = [tdo_enable<<7][eop_gen<<6][N[14:13]]
CMD_SHORT_CUSTOM_TMS_TDI      100    ceil(n/4)        Custom TMS+TDI shift, 1..32 bits.
                                                      Each payload byte carries 4 TMS bits in the
                                                      high nibble and 4 TDI bits in the low nibble,
                                                      LSB-first within each nibble.
CMD_LONG_FIXED_TMS_CUSTOM_TDI 101    1+ceil(n/8)      TMS held to 0, custom TDI; 1..8192 bits.
                                                      Byte 0 low5 = N[4:0]; byte 1 = N[12:5];
                                                      payload follows, 8 TDI bits per byte LSB-first.
CMD_LONG_FIXED_TMS_TDI        110    1                TMS=0, TDI=0; 1..8192 idle ticks.
                                                      Same length encoding, no TDI payload.
============================  =====  ===============  =============================================

Response stream
---------------

Captured TDO bits are emitted on the T2H data channel, packed
LSB-first into bytes. The TDO-enable FIFO is 2 entries deep on-chip
(see :data:`TDO_FIFO_DEPTH`); the host must not push a third capture
window before the first one drains. Each FIFO entry has an optional
``eop_gen`` flag — when the entry's window completes, the on-chip hub
sets EOP on the next response byte boundary.

The decoder produced here translates a complete command stream into a
list of :class:`Op` instances. The encoder packs an iterable of
captured bits into bytes plus EOP positions.
"""

from dataclasses import dataclass

from ..bitstring import BitString


# --- Opcodes (3-bit, occupy bits [7:5] of the command byte) ---

CMD_CONFIG = 0b000
CMD_WRITE_TDO_ENABLE_FIFO = 0b010
CMD_SHORT_CUSTOM_TMS_TDI = 0b100
CMD_LONG_FIXED_TMS_CUSTOM_TDI = 0b101
CMD_LONG_FIXED_TMS_TDI = 0b110

# CMD_CONFIG sub-opcodes (low 2 bits of command byte)
CONFIG_RETRIEVE_INFO = 0b00
CONFIG_RESET_TDO_FIFO = 0b01

# Single-byte response from CONFIG_RETRIEVE_INFO. HDL layout:
#   bits [7:4] CONFIG_RESPONSE_RESERVED (currently 0)
#   bits [3:0] VERSION (currently 0)
CONFIG_INFO_RESPONSE_BYTE = 0x00

# Hardware FIFO depth for capture-window descriptors.
TDO_FIFO_DEPTH = 2

# Maximum bit counts encodable in each command (count = field + 1).
SHORT_MAX_BITS = 32
LONG_MAX_BITS = 8192


# --- Decoded operations ---


@dataclass
class RetrieveInfo:
    """CMD_CONFIG with sub-op = retrieve info. Caller must emit
    :data:`CONFIG_INFO_RESPONSE_BYTE` on T2H."""


@dataclass
class ResetTdoFifo:
    """CMD_CONFIG with sub-op = reset TDO-enable FIFO. Caller must
    drop any pending capture descriptors."""


@dataclass
class PushTdoCapture:
    """CMD_WRITE_TDO_ENABLE_FIFO. Schedule one capture window."""

    duration: int      # number of TCKs the entry covers (1..32768)
    tdo_enable: bool   # if False, the window passes through with no capture
    eop_gen: bool      # if True, set EOP on the response byte completing this window


@dataclass
class Shift:
    """A shift of ``num_bits`` TCKs. Always equal-length tms and tdi.

    For CMD_LONG_FIXED_TMS_TDI, both vectors are all zeros.
    For CMD_LONG_FIXED_TMS_CUSTOM_TDI, ``tms`` is all zeros and ``tdi``
    carries the custom data. For CMD_SHORT_CUSTOM_TMS_TDI both are
    custom.
    """

    tms: BitString
    tdi: BitString

    @property
    def num_bits(self):
        return len(self.tms)


# --- Decoder ---


class _Truncated(Exception):
    """Raised internally when the byte buffer ends mid-command."""


class JopDecoder:
    """Stateful decoder for the H2T JoP byte stream.

    Holds whatever bytes haven't yet completed a command across calls
    to :meth:`feed`, so the caller can hand it raw H2T payloads as
    they arrive without packet-alignment guarantees.
    """

    def __init__(self):
        self._buf = bytearray()

    def feed(self, data):
        """Append bytes and return any newly completed ops."""
        self._buf.extend(data)
        ops = []
        while self._buf:
            try:
                op, consumed = self._decode_one(self._buf)
            except _Truncated:
                break
            ops.append(op)
            del self._buf[:consumed]
        return ops

    @property
    def pending_bytes(self):
        """Bytes held back waiting for command completion."""
        return len(self._buf)

    @staticmethod
    def _decode_one(buf):
        if not buf:
            raise _Truncated
        first = buf[0]
        opcode = (first >> 5) & 0x7

        if opcode == CMD_CONFIG:
            sub = first & 0x3
            if sub == CONFIG_RETRIEVE_INFO:
                return RetrieveInfo(), 1
            if sub == CONFIG_RESET_TDO_FIFO:
                return ResetTdoFifo(), 1
            raise ValueError(f"unknown CMD_CONFIG sub-op {sub:#04b}")

        if opcode == CMD_WRITE_TDO_ENABLE_FIFO:
            if len(buf) < 3:
                raise _Truncated
            duration_low5 = first & 0x1F
            duration_mid8 = buf[1]
            third = buf[2]
            tdo_enable = bool(third & 0x80)
            eop_gen = bool(third & 0x40)
            duration_top2 = third & 0x3
            duration_field = (duration_top2 << 13) | (duration_mid8 << 5) | duration_low5
            return PushTdoCapture(
                duration=duration_field + 1,
                tdo_enable=tdo_enable,
                eop_gen=eop_gen,
            ), 3

        if opcode == CMD_SHORT_CUSTOM_TMS_TDI:
            n_bits = (first & 0x1F) + 1
            n_data = (n_bits + 3) // 4  # 4 bits of TMS+TDI per byte
            if len(buf) < 1 + n_data:
                raise _Truncated
            tms_bits = []
            tdi_bits = []
            for byte in buf[1:1 + n_data]:
                # Within each nibble, LSB shifts out first.
                tdi_bits += [(byte >> b) & 1 for b in range(4)]
                tms_bits += [(byte >> (4 + b)) & 1 for b in range(4)]
            tms = _bits_to_bs(tms_bits[:n_bits])
            tdi = _bits_to_bs(tdi_bits[:n_bits])
            return Shift(tms=tms, tdi=tdi), 1 + n_data

        if opcode in (CMD_LONG_FIXED_TMS_CUSTOM_TDI, CMD_LONG_FIXED_TMS_TDI):
            if len(buf) < 2:
                raise _Truncated
            n_bits = ((buf[1] << 5) | (first & 0x1F)) + 1
            if opcode == CMD_LONG_FIXED_TMS_TDI:
                tms = BitString(0, n_bits)
                tdi = BitString(0, n_bits)
                return Shift(tms=tms, tdi=tdi), 2
            n_data = (n_bits + 7) // 8
            if len(buf) < 2 + n_data:
                raise _Truncated
            tdi_payload = bytes(buf[2:2 + n_data])
            tdi = BitString(tdi_payload, n_bits)
            tms = BitString(0, n_bits)
            return Shift(tms=tms, tdi=tdi), 2 + n_data

        raise ValueError(f"unknown JoP opcode {opcode:#05b}")


# --- Encoder ---


class JopEncoder:
    """Pack captured TDO bits LSB-first into T2H bytes.

    Tracks an offset within the current byte across multiple
    :meth:`emit_window` calls so windows can extend across byte
    boundaries. ``eop_at`` records byte indices where the on-chip
    ``set_eop`` would fire (when the TDO-enable FIFO entry's
    ``eop_gen`` flag is set).
    """

    def __init__(self):
        self._byte = 0
        self._bit_pos = 0  # bits already written into _byte

    def emit_window(self, tdo, *, eop=False):
        """Pack ``tdo`` into bytes and optionally mark the final byte
        as carrying EOP. Returns ``(bytes, eop_indices)``.

        Partial bytes left over after this window are kept and merged
        with the next call; their offsets continue accumulating.
        """
        out = bytearray()
        for i in range(len(tdo)):
            self._byte |= int(tdo[i]) << self._bit_pos
            self._bit_pos += 1
            if self._bit_pos == 8:
                out.append(self._byte)
                self._byte = 0
                self._bit_pos = 0
        eop_indices = []
        if eop:
            # On-chip behaviour: EOP is asserted on the next response
            # byte boundary. If we're mid-byte, flush it; the EOP is on
            # the byte we just emitted.
            if self._bit_pos > 0:
                out.append(self._byte)
                self._byte = 0
                self._bit_pos = 0
            if out:
                eop_indices.append(len(out) - 1)
        return bytes(out), eop_indices

    def flush(self):
        """Emit any held partial byte. Caller decides when (e.g. on
        connection close)."""
        if self._bit_pos == 0:
            return b""
        out = bytes([self._byte])
        self._byte = 0
        self._bit_pos = 0
        return out


# --- Helpers ---


def _bits_to_bs(bits):
    out = BitString()
    for b in bits:
        out += BitString(b, 1)
    return out


def encode_short_custom_tms_tdi(tms, tdi):
    """Encode a CMD_SHORT_CUSTOM_TMS_TDI command (1..32 bits)."""
    n = len(tms)
    if n == 0 or n > SHORT_MAX_BITS:
        raise ValueError(f"SHORT shift size out of range: {n}")
    if len(tdi) != n:
        raise ValueError("tms/tdi length mismatch")
    header = (CMD_SHORT_CUSTOM_TMS_TDI << 5) | ((n - 1) & 0x1F)
    out = bytearray([header])
    for off in range(0, n, 4):
        chunk = min(4, n - off)
        byte = 0
        for b in range(chunk):
            byte |= (int(tdi[off + b]) & 1) << b
            byte |= (int(tms[off + b]) & 1) << (4 + b)
        out.append(byte)
    return bytes(out)


def encode_long_fixed_tms_custom_tdi(tdi):
    """Encode a CMD_LONG_FIXED_TMS_CUSTOM_TDI command (1..8192 bits)."""
    n = len(tdi)
    if n == 0 or n > LONG_MAX_BITS:
        raise ValueError(f"LONG shift size out of range: {n}")
    field = n - 1
    out = bytearray([
        (CMD_LONG_FIXED_TMS_CUSTOM_TDI << 5) | (field & 0x1F),
        (field >> 5) & 0xFF,
    ])
    out += bytes(tdi.data).ljust((n + 7) // 8, b"\x00")
    return bytes(out)


def encode_long_fixed_tms_tdi(num_bits):
    """Encode a CMD_LONG_FIXED_TMS_TDI command (1..8192 idle ticks)."""
    if num_bits <= 0 or num_bits > LONG_MAX_BITS:
        raise ValueError(f"LONG idle size out of range: {num_bits}")
    field = num_bits - 1
    return bytes([
        (CMD_LONG_FIXED_TMS_TDI << 5) | (field & 0x1F),
        (field >> 5) & 0xFF,
    ])


def encode_write_tdo_enable_fifo(duration, *, tdo_enable, eop_gen):
    """Encode a CMD_WRITE_TDO_ENABLE_FIFO command."""
    if duration <= 0 or duration > (1 << 15):
        raise ValueError(f"capture duration out of range: {duration}")
    field = duration - 1
    return bytes([
        (CMD_WRITE_TDO_ENABLE_FIFO << 5) | (field & 0x1F),
        (field >> 5) & 0xFF,
        ((1 if tdo_enable else 0) << 7)
        | ((1 if eop_gen else 0) << 6)
        | ((field >> 13) & 0x3),
    ])


def encode_retrieve_info():
    return bytes([(CMD_CONFIG << 5) | CONFIG_RETRIEVE_INFO])


def encode_reset_tdo_fifo():
    return bytes([(CMD_CONFIG << 5) | CONFIG_RESET_TDO_FIFO])
