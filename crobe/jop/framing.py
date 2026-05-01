"""Avalon-ST over TCP packet framing for JoP / etherlink data sockets.

Each H2T / T2H / MGMT / MGMT_RSP packet on the wire is::

    guardband:   4 bytes = DE AD BE EF
    header:      6 bytes (see below, little-endian)
    payload:     DATA_LEN_BYTES bytes

Header layout for H2T/T2H::

    byte 0   SOP_EOP   (bit0=SOP, bit1=EOP)
    byte 1   CONN_ID
    byte 2-3 CHANNEL    (u16 LE, masked 0x07FF)
    byte 4-5 DATA_LEN   (u16 LE, max 0x1000 = 4096 bytes for H2T)

Header layout for MGMT/MGMT_RSP — same shape, but byte 1 is reserved
(zero) and DATA_LEN can be up to 0xFFFF (64 KB).

The payload bytes are opaque at this layer — for H2T/T2H they are the
JoP byte stream; for MGMT they are whatever Quartus uses for sideband
configuration (we don't decode them yet).
"""

from dataclasses import dataclass
import struct


GUARDBAND = b"\xde\xad\xbe\xef"
SIZEOF_PACKET_GUARDBAND = 4
SIZEOF_H2T_HEADER = 6
SIZEOF_MGMT_HEADER = 6

# Max payload sizes per Intel's intel_st_debug_if_packet.h.
H2T_MAX_PAYLOAD = 0x1000
MGMT_MAX_PAYLOAD = 0xFFFF

# SOP/EOP bit positions inside byte 0.
FLAG_SOP = 0x01
FLAG_EOP = 0x02


class GuardbandError(Exception):
    """Raised when the expected guardband prefix isn't found on the wire."""


@dataclass
class H2tPacket:
    """One H2T or T2H packet.

    Both directions use the same header layout (Quartus reuses
    H2T_PACKET_HEADER for T2H — see Intel's source).
    """

    sop: bool
    eop: bool
    conn_id: int
    channel: int
    payload: bytes

    def encode(self):
        if len(self.payload) > H2T_MAX_PAYLOAD:
            raise ValueError(
                f"H2T payload too long: {len(self.payload)} > {H2T_MAX_PAYLOAD}")
        if not 0 <= self.channel <= 0x07FF:
            raise ValueError(f"channel out of range: {self.channel}")
        if not 0 <= self.conn_id <= 0xFF:
            raise ValueError(f"conn_id out of range: {self.conn_id}")
        flags = (FLAG_SOP if self.sop else 0) | (FLAG_EOP if self.eop else 0)
        header = struct.pack(
            "<BBHH", flags, self.conn_id & 0xFF,
            self.channel & 0xFFFF, len(self.payload) & 0xFFFF)
        return GUARDBAND + header + self.payload

    @classmethod
    def decode_header(cls, header_bytes):
        """Parse the 6-byte header following the guardband. Returns
        ``(sop, eop, conn_id, channel, data_len)``."""
        if len(header_bytes) != SIZEOF_H2T_HEADER:
            raise ValueError(f"H2T header must be {SIZEOF_H2T_HEADER} bytes")
        flags, conn_id, channel, data_len = struct.unpack("<BBHH", header_bytes)
        return (
            bool(flags & FLAG_SOP),
            bool(flags & FLAG_EOP),
            conn_id,
            channel & 0x07FF,
            data_len,
        )


@dataclass
class MgmtPacket:
    """One MGMT or MGMT_RSP packet."""

    sop: bool
    eop: bool
    channel: int
    payload: bytes

    def encode(self):
        if len(self.payload) > MGMT_MAX_PAYLOAD:
            raise ValueError(
                f"MGMT payload too long: {len(self.payload)} > {MGMT_MAX_PAYLOAD}")
        if not 0 <= self.channel <= 0x07FF:
            raise ValueError(f"channel out of range: {self.channel}")
        flags = (FLAG_SOP if self.sop else 0) | (FLAG_EOP if self.eop else 0)
        # Byte 1 is reserved (zero) on MGMT.
        header = struct.pack(
            "<BBHH", flags, 0,
            self.channel & 0xFFFF, len(self.payload) & 0xFFFF)
        return GUARDBAND + header + self.payload

    @classmethod
    def decode_header(cls, header_bytes):
        """Parse the 6-byte MGMT header. Returns
        ``(sop, eop, channel, data_len)``."""
        if len(header_bytes) != SIZEOF_MGMT_HEADER:
            raise ValueError(f"MGMT header must be {SIZEOF_MGMT_HEADER} bytes")
        flags, _reserved, channel, data_len = struct.unpack(
            "<BBHH", header_bytes)
        return (
            bool(flags & FLAG_SOP),
            bool(flags & FLAG_EOP),
            channel & 0x07FF,
            data_len,
        )


class FrameBuffer:
    """Accumulates bytes from a non-blocking ``recv`` and yields complete
    frames. One per readable socket — one for H2T, one for MGMT, one for
    CTRL (CTRL uses :meth:`take_until_nul` rather than packet framing).
    """

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        """Append bytes received from the socket."""
        self.buf.extend(data)

    def take_until_nul(self):
        """Pop and return one NUL-terminated chunk (without the NUL),
        or ``None`` if no NUL is in the buffer yet."""
        idx = self.buf.find(b"\0")
        if idx < 0:
            return None
        out = bytes(self.buf[:idx])
        del self.buf[:idx + 1]
        return out

    def take_h2t_packet(self):
        """Pop and return one H2tPacket, or ``None`` if not enough bytes
        yet. Raises :class:`GuardbandError` on bad guardband."""
        if len(self.buf) < SIZEOF_PACKET_GUARDBAND + SIZEOF_H2T_HEADER:
            return None
        if bytes(self.buf[:SIZEOF_PACKET_GUARDBAND]) != GUARDBAND:
            raise GuardbandError(
                f"bad guardband: {bytes(self.buf[:SIZEOF_PACKET_GUARDBAND])!r}")
        header = bytes(self.buf[SIZEOF_PACKET_GUARDBAND
                                :SIZEOF_PACKET_GUARDBAND + SIZEOF_H2T_HEADER])
        sop, eop, conn_id, channel, data_len = H2tPacket.decode_header(header)
        if data_len > H2T_MAX_PAYLOAD:
            raise ValueError(f"H2T data_len out of range: {data_len}")
        total = SIZEOF_PACKET_GUARDBAND + SIZEOF_H2T_HEADER + data_len
        if len(self.buf) < total:
            return None
        payload = bytes(self.buf[SIZEOF_PACKET_GUARDBAND + SIZEOF_H2T_HEADER:total])
        del self.buf[:total]
        return H2tPacket(sop=sop, eop=eop, conn_id=conn_id,
                         channel=channel, payload=payload)

    def take_mgmt_packet(self):
        """Pop and return one MgmtPacket, or ``None`` if not enough bytes
        yet. Raises :class:`GuardbandError` on bad guardband."""
        if len(self.buf) < SIZEOF_PACKET_GUARDBAND + SIZEOF_MGMT_HEADER:
            return None
        if bytes(self.buf[:SIZEOF_PACKET_GUARDBAND]) != GUARDBAND:
            raise GuardbandError(
                f"bad guardband: {bytes(self.buf[:SIZEOF_PACKET_GUARDBAND])!r}")
        header = bytes(self.buf[SIZEOF_PACKET_GUARDBAND
                                :SIZEOF_PACKET_GUARDBAND + SIZEOF_MGMT_HEADER])
        sop, eop, channel, data_len = MgmtPacket.decode_header(header)
        if data_len > MGMT_MAX_PAYLOAD:
            raise ValueError(f"MGMT data_len out of range: {data_len}")
        total = SIZEOF_PACKET_GUARDBAND + SIZEOF_MGMT_HEADER + data_len
        if len(self.buf) < total:
            return None
        payload = bytes(self.buf[SIZEOF_PACKET_GUARDBAND + SIZEOF_MGMT_HEADER:total])
        del self.buf[:total]
        return MgmtPacket(sop=sop, eop=eop,
                          channel=channel, payload=payload)
