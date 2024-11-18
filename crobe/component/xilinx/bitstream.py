import struct
import enum
from dataclasses import dataclass
from ...util.crc import Crc
import datetime
import io

crc_class = Crc.from_name("CRC-32/ISCSI")

class Command(enum.IntEnum):
    NULL      = 0b00000
    WCFG      = 0b00001
    MFW       = 0b00010
    DGHIGH    = 0b00011
    RCFG      = 0b00100
    START     = 0b00101
    RCAP      = 0b00110
    RCRC      = 0b00111
    AGHIGH    = 0b01000
    SWITCH    = 0b01001
    GRESTORE  = 0b01010
    SHUTDOWN  = 0b01011
    GCAPTURE  = 0b01100
    DESYNC    = 0b01101
    IPROG     = 0b01111
    CRCC      = 0b10000
    LTIMER    = 0b10001
    BSPI_READ = 0b10010
    FALL_EDGE = 0b10011

class Address(enum.IntEnum):
    CRC        = 0
    FAR        = 1
    FDRI       = 2
    FDRO       = 3
    CMD        = 4
    CTL0       = 5
    MASK       = 6
    STAT       = 7
    LOUT       = 8
    COR0       = 9
    MFWR       = 10
    CBC        = 11
    IDCODE     = 12
    AXSS       = 13
    COR1       = 14
    UNKNOWN_15 = 15
    WBSTAR     = 16
    TIMER      = 17
    UNKNOWN_18 = 18
    POST_CRC   = 19
    UNKNOWN_20 = 20
    UNKNOWN_21 = 21
    BOOTSTS    = 22
    CTL1       = 24
    UNKNOWN_30 = 30
    BSPI       = 31

    @property
    def has_data(self):
        return bool((1 << int(self)) & 0x4)
        
class Opcode(enum.IntEnum):
    NOOP = 0
    READ = 1
    WRITE = 2

class Packet:
    def __init__(self, type, opcode, address, data):
        self.type = type
        self.opcode = opcode
        self.address = address
        self.data = data

    def words(self):
        if self.type == 7:
            yield 0xffffffff
            return

        elif self.type == 2:
            yield ((1 << 29)
                   | (int(self.opcode) << 27)
                   | (int(self.address) << 13))
            yield ((2 << 29)
                   | (int(self.opcode) << 27)
                   | len(self.data))

        elif self.type == 1:
            yield ((1 << 29)
                   | (int(self.opcode) << 27)
                   | (int(self.address) << 13)
                   | len(self.data))

        else:
            raise ValueError(f"{self.type=}")
        for d in self.data:
            yield d

    def __str__(self):
        if self.opcode == Opcode.NOOP:
            return f'<t{self.type} {self.opcode.name}>'
        if self.data:
            return f'<t{self.type} {self.opcode.name} {self.address.name} {len(self.data)} words>'
        else:
            return f'<t{self.type} {self.opcode.name} {self.address.name}>'
            
    @classmethod
    def from_words(cls, word_iterator):
        word = next(word_iterator)

        if word == 0xffffffff:
            return cls(7, 0, 0, [])

        try:
            type = word >> 29
            opcode = Opcode((word >> 27) & 0x3)
            address = Address((word >> 13) & 0x1F)
            word_count = word & 0x7FF
        except:
            #print(hex(word))
            raise
        
        if type == 1 and word_count == 0 and address.has_data and opcode == Opcode.WRITE:
            sword = next(word_iterator)
            stype = sword >> 29
            sopcode = Opcode((sword >> 27) & 0x3)
            sword_count = sword & 0x07FFFFFF

            assert stype == 2 and sopcode == opcode and sword_count
            word_count = sword_count
            type = stype
        elif type == 2:
            raise ValueError(type)
            
        data = [next(word_iterator) for i in range(word_count)]

        return cls(type, opcode, address, data)

    @property
    def command(self):
        assert self.opcode == Opcode.WRITE and self.address == Address.CMD
        return Command(self.data[0])
    
    def crc_update(self, state):
        if self.opcode != Opcode.WRITE:
            return state

        if self.address == Address.CMD and self.command == Command.RCRC:
            return crc_class.init

        if self.address == Address.CRC:
            return crc_class.init

        if self.address in [
            Address.UNKNOWN_15,
            Address.UNKNOWN_18,
            Address.UNKNOWN_20,
            Address.UNKNOWN_21,
            Address.BOOTSTS
        ]:
            return state

        for data in self.data:
            for i in range(32):
                state = crc_class._forward(state, data & 1)
                data >>= 1
            address = int(self.address)
            for i in range(5):
                state = crc_class._forward(state, address & 1)
                address >>= 1
        return state

    def does_clear_crc(self):
        if self.opcode != Opcode.WRITE:
            return False

        return (self.address == Address.CMD and self.command == Command.RCRC) \
            or self.address == Address.CRC

    def is_crc_transparent(self):
        return self.opcode != Opcode.WRITE \
            or self.address in [
                Address.UNKNOWN_15,
                Address.UNKNOWN_18,
                Address.UNKNOWN_20,
                Address.UNKNOWN_21,
                Address.BOOTSTS
            ]

    @property
    def crc_bit_width(self):
        return 37 * len(self.data)

    @property
    def crc_value(self):
        state = 0
        for data in self.data:
            for i in range(32):
                state = crc_class._forward(state, data & 1)
                data >>= 1
            address = int(self.address)
            for i in range(5):
                state = crc_class._forward(state, address & 1)
                address >>= 1
        return state

class Bitstream:
    SYNC_HEADER = [0xffffffff, 0xffffffff,
                   0x000000bb, 0x11220044,
                   0xffffffff, 0xffffffff,
                   0xaa995566]

    @classmethod
    def config_word_iterator(cls, data):
        sync = struct.pack(">7L", *cls.SYNC_HEADER)

        point = data.index(sync) + len(sync)

        while point < len(data) - 3:
            w = int.from_bytes(data[point:point+4], "big")
            #print(hex(w))
            yield w
            point += 4

    def __init__(self, packets, header_info):
        self.packets = packets
        self.header_info = header_info

    @classmethod
    def from_loadable(cls, loadable):
        packets = []
        config_words = cls.config_word_iterator(loadable[0].data)

        crc_state = crc_class.init
        while True:
            try:
                packet = Packet.from_words(config_words)
            except StopIteration:
                break

            #print(packet)
            
            if packet.opcode == Opcode.WRITE and packet.address == Address.CRC:
                assert packet.data[0] == crc_class.as_int(crc_state)

            packets.append(packet)
            crc_state = packet.crc_update(crc_state)

        header_data = {}
        for field in ["build_date", "device", "project", "userid", "version", "compress"]:
            try:
                header_data[field] = loadable.info[field]
            except:
                pass
            
        return cls(packets, header_data)

    def crc_validate(self):
        crc_state = crc_class.init
        for packet in self.packets:
            if packet.opcode == Opcode.WRITE and packet.address == Address.CRC:
                assert packet.data[0] == crc_class.as_int(crc_state)

            packets.append(packet)
            crc_state = packet.crc_update(crc_state)

    def crc_validate(self):
        state = crc_class.init
        for packet in self.packets:
            if packet.opcode == Opcode.WRITE and packet.address == Address.CRC:
                got = packet.data[0]
                expected = crc_class.as_int(state)
                delta = got ^ expected
                if packet.data[0] != crc_class.as_int(state):
                    raise ValueError(f"{expected=:#010x}, {got=:#010x}, {delta=:#010x}")
            state = packet.crc_update(state)

    def with_idcode(self, idcode):
        crc_offsets = {}
        offset = 0
        for packet in self.packets[::-1]:
            if not packet.is_crc_transparent():
                offset += packet.crc_bit_width

            if packet.does_clear_crc():
                offset = 0
            else:
                crc_offsets[packet] = offset

        delta = 0

        ret = self.__class__([], self.header_info)

        for packet in self.packets:
            if packet.opcode == Opcode.WRITE and packet.address == Address.IDCODE:
                p = Packet(packet.type, packet.opcode, packet.address, [idcode])
                raw_diff = idcode ^ packet.data[0]

                for i in range(32):
                    if raw_diff & (1 << i):
                        delta ^= crc_class.as_int(crc_class._contribution_at_bit(crc_offsets[packet]-1-i))

            elif packet.opcode == Opcode.WRITE and packet.address == Address.CRC:
                p = Packet(packet.type, packet.opcode, packet.address, [packet.data[0] ^ delta])
                delta = 0

            else:
                p = packet

            ret.packets.append(p)

        return ret

    BIT_PREAMBLE = b'\x00\x09\x0f\xf0\x0f\xf0\x0f\xf0\x0f\xf0\x00\x00\x01'

    def to_bit(self):
        f = io.BytesIO()

        f.write(self.BIT_PREAMBLE)
        build_date = self.header_info.get("build_date", datetime.datetime.now())
        device = self.header_info.get("device", "unknown")
        project = self.header_info.get("project", "unknown")
        compress = self.header_info.get("compress")
        userid = self.header_info.get("userid")
        version = self.header_info.get("version")

        if compress:
            project += f";COMPRESS={compress}"
        if userid:
            project += f";UserID={userid:8X}"
        if version:
            project += f";Version={version}"

        parts = dict(
            a = project,
            b = device,
            c = build_date.date().strftime("%Y/%m/%d"),
            d = build_date.time().strftime("%H:%M:%S"),
            )

        for key, value in sorted(parts.items()):
            value = value.encode("utf-8") + b'\x00'
            f.write(struct.pack('>BH', ord(key), len(value)))
            f.write(value)

        bitstream_words = []
        for i in range(6):
            bitstream_words.append(0xffffffff)
        for i in self.SYNC_HEADER:
            bitstream_words.append(i)
        for packet in self.packets:
            for w in packet.words():
                bitstream_words.append(w)
        bitstream_data = struct.pack(f">{len(bitstream_words)}L", *bitstream_words)

        f.write(struct.pack('>cL', b'e', len(bitstream_data)))
        f.write(bitstream_data)

        return f.getbuffer()
