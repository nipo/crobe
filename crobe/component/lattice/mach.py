from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from ...util.endian import bitswap8
import struct
from ... import bitstring
import datetime
import time
import binascii

class Frame:
    def __init__(self, data, crc = None):
        self.data = data
        self.crc = crc

class BsReader:
    def __init__(self, blob):
        self.blob = blob
        self.point = 0

    def get(self, count):
        if not count:
            return b''
        r = self.blob[self.point : self.point + count]
        self.point += count
        if self.point > len(self.blob):
            raise ValueError("Read overflow")
        return r

    def big_get(self, count):
        return int.from_bytes(self.get(count), "big")

    def inc_get(self, count, crc, padding, frame_bit_size):
        frame_byte_size = (frame_bit_size + 7) // 8
        ret = []
        c = None
        for i in range(count):
            data = bitswap8(self.get(frame_byte_size))
            if crc:
                c = self.big_get(2)
            ret.append(Frame(data, c))
            padding = self.get(padding)
        return ret

    def __bool__(self):
        return self.point != len(self.blob)

class MachXOBitstream:
    HEADER = bytes([0xff, 0xff, 0xbd, 0xb3, 0xff, 0xff])

    def __init__(self, prog):
        reader = BsReader(prog.segment_at(0).data)

        if "Part" not in prog.info:
            raise ValueError("Can only parse bitstream with ASCII header")

        if reader.get(len(self.HEADER)) != self.HEADER:
            raise ValueError("Bitstream data does not start with expected header")

        part = "-".join(prog.info["Part"].split("-")[:2])
        
        self.info = [p for p in PARTS if p.name == part][0]
        self.rti = []
        self.ebr = {}
        self.usercode = 0
        ebr_addr = 0

        assert self.info.col_bit_count == int(prog.info["Cols"])
        assert self.info.row_count == int(prog.info["Rows"])
        
        while reader:
            cmd = reader.big_get(1)
        
            if cmd == 0xff:
                continue

            args = reader.big_get(3)
        
            if cmd == MachXO2.IR_LSC_RESET_CRC:
                pass

            elif cmd == MachXO2.IR_VERIFY_ID:
                idcode = reader.big_get(4)
                assert idcode == self.info.idcode

            elif cmd == MachXO2.IR_LSC_WRITE_COMP_DIC:
                raise NotImplementedError("Compressed bitstream support not implemented")
                reader.get(8)

            elif cmd == MachXO2.IR_LSC_PROG_CTRL0:
                reader.get(4)

            elif cmd == MachXO2.IR_LSC_INIT_ADDRESS:
                addr = 0

            elif cmd == MachXO2.IR_LSC_PROG_INCR_RTI:
                padding = 0 if (args & 0x200000) else (((args >> 16) & 0xf) if args & 0x100000 else 1)

                rows = reader.inc_get(args & 0xffff, not (args & 0x400000), padding, self.info.col_bit_count)
                self.rti = rows

            elif cmd == MachXO2.IR_LSC_PROG_INCR_CMP:
                raise NotImplementedError("Compressed bitstream support not implemented")
                reader.get(8)

            elif cmd == MachXO2.IR_LSC_PROG_SED_CRC:
                reader.get(4)

            elif cmd == MachXO2.IR_ISC_PROGRAM_SECURITY:
                pass

            elif cmd == MachXO2.IR_ISC_PROGRAM_USERCODE:
                self.usercode = reader.big_get(4)

            elif cmd == MachXO2.IR_LSC_WRITE_BUS_ADDRESS:
                ebr_addr = reader.big_get(4)

            elif cmd == MachXO2.IR_LSC_EBR_WRITE:
                padding = 0 if (args & 0x200000) else (((args >> 16) & 0xf) if args & 0x100000 else 1)

                rows = reader.inc_get(args & 0xffff, bool(args & 0x400000), padding, 72)
                self.ebr[ebr_addr] = rows

            elif cmd == MachXO2.IR_ISC_PROGRAM_DONE:
                pass

            elif cmd == MachXO2.IR_LSC_PCS_WRITE:
                reader.big_get(args & 0xff)

            else:
                raise ValueError("UNKNOWN: %02x" % cmd, point)
        
            if args & 0x800000:
                reader.big_get(2)

class MachXO2Info:
    def __init__(self, idcode, name, col_bit_count, row_count, flash_page_count, ufm_page_count):
        self.idcode = idcode
        self.name = name
        self.col_bit_count = col_bit_count
        self.row_count = row_count
        self.flash_page_count = flash_page_count
        self.ufm_page_count = ufm_page_count

# Relevant info in data/vmdata/database/xpga/xo2/{ispVM_018a.xdf,XO2.svp}
PARTS = [
    MachXO2Info(0x012B0043, "LCMXO2-256ZE", 504, 186, 575, 0),
    MachXO2Info(0x012B8043, "LCMXO2-256HC", 504, 186, 575, 0),
    MachXO2Info(0x012B1043, "LCMXO2-640ZE", 888, 215, 1151, 192),
    MachXO2Info(0x012B9043, "LCMXO2-640HC", 888, 215, 1151, 192),
    MachXO2Info(0x012BA043, "LCMXO2-640UHC", 1080, 333, 2175, 512),
    MachXO2Info(0x012B2043, "LCMXO2-1200ZE", 1080, 333, 2175, 512),
    MachXO2Info(0x012BA043, "LCMXO2-1200HC", 1080, 333, 2175, 512),
    MachXO2Info(0x012B3043, "LCMXO2-2000ZE", 1272, 420, 3198, 640),
    MachXO2Info(0x012BB043, "LCMXO2-1200UHC", 1272, 420, 3198, 640),
    MachXO2Info(0x012BB043, "LCMXO2-2000HC", 1272, 420, 3198, 640),
    MachXO2Info(0x012B3043, "LCMXO2-2000HE", 1272, 420, 3198, 640),
    MachXO2Info(0x012B4043, "LCMXO2-4000ZE", 1560, 623, 5758, 768),
    MachXO2Info(0x012BC043, "LCMXO2-2000UHC", 1560, 623, 5758, 768),
    MachXO2Info(0x012BC043, "LCMXO2-4000HC", 1560, 623, 5758, 768),
    MachXO2Info(0x012B4043, "LCMXO2-2000UHE", 1560, 623, 5758, 768),
    MachXO2Info(0x012B4043, "LCMXO2-4000HE", 1560, 623, 5758, 768),
    MachXO2Info(0x012B5043, "LCMXO2-7000HE", 1992, 770, 9212, 2048),
    MachXO2Info(0x012B5043, "LCMXO2-7000ZE", 1992, 770, 9212, 2048),
    MachXO2Info(0x012BD043, "LCMXO2-4000UHC", 1992, 770, 9212, 2048),
    MachXO2Info(0x012BD043, "LCMXO2-7000HC", 1992, 770, 9212, 2048),
]        

@jtag.Tap.db.register(*set([PartId.from_idcode(p.idcode).drop_revision() for p in PARTS]))
class MachXO2(jtag.Tap):
    irlen = 8
    max_freq = 25e6

    class Status(bitfield.Register):
        name = "Status"
        fields = [
            bitfield.BinaryField("Transparent mode", 0, "No", "Yes"),
            bitfield.Field("Target", (1, 3), {0: "SRAM", 1: "EFUSE", 2: "Feature", 4:"Flash"}),
            bitfield.EnableField("JTAG", 4),
            bitfield.BinaryField("Logic is pw prot.", 5, "No", "Yes"),
            bitfield.EnableField("SRAM OTP", 6),
            bitfield.EnableField("Decrypt", 7),
            bitfield.BinaryField("Done", 8, "No", "Yes"),
            bitfield.EnableField("ISC", 9),
            bitfield.EnableField("Write", 10),
            bitfield.EnableField("Read", 11),
            bitfield.BinaryField("Busy", 12, "No", "Yes"),
            bitfield.BinaryField("Fail", 13, "No", "Yes"),
            bitfield.BinaryField("Feature OTP", 14, "No", "Yes"),
            bitfield.BinaryField("Decrypt only", 15, "No", "Yes"),
            bitfield.EnableField("Passw prot.", 16),
            bitfield.EnableField("UFM OTP", 17),
            bitfield.EnableField("Assp", 18),
            bitfield.EnableField("Sdmen", 19),
            bitfield.BinaryField("Enc. preamble", 20, "none", "detected"),
            bitfield.BinaryField("Std. Pream", 21, "none", "detected"),
            bitfield.BinaryField("SPI", 22, "OK", "Fail"),
            bitfield.Field("Error", (23, 25), ["OK", "ID", "Bad command", "CRC", "Preamble", "Abort", "Overflow", "SRAM ovr."]),
            bitfield.BinaryField("Execution error", 26, "No", "Yes"),
            bitfield.BinaryField("ID Mismatch", 27, "No", "Yes"),
            bitfield.BinaryField("Invalid Command", 28, "No", "Yes"),
            bitfield.BinaryField("SED Error", 29, "No", "Yes"),
            bitfield.BinaryField("Bypass", 30, "No", "Yes"),
            bitfield.BinaryField("Flow through mode", 31, "No", "Yes"),
            ]

    class Ctrl0(bitfield.Register):
        name = "Control 0"
        fields = [
            bitfield.ValueField("Master clock Freq", (0, 5)),
            bitfield.ValueField("SPI Mode", (6, 7)),
            bitfield.BinaryField("SPI bit order", 8, "MSB First", "LSB First"),
            bitfield.ValueField("MCLKB", 9),
            bitfield.ValueField("STX DUM", (10, 11)),
            bitfield.ValueField("DONE", (12, 14)),
            bitfield.ValueField("INIT", (15, 17)),
            bitfield.ValueField("P_DONE", (18, 19)),
            bitfield.EnableField("SPI Master", 20),
            bitfield.EnableField("SPI Slave Slow Respond Mode", 21),
            bitfield.BinaryField("CPU Mon", 22, "No", "Yes"),
            bitfield.BinaryField("SSPI Auto", 23, "No", "Yes"),
            bitfield.BinaryField("HFC", 24, "No", "Yes"),
            bitfield.BinaryField("TranEdit", 25, "No", "Yes"),
            bitfield.DisableField("CDM", 26),
            bitfield.DisableField("BKE", 27),
            bitfield.BinaryField("NDR", 28, "No", "Yes"),
            bitfield.BinaryField("Wake Up", 29, "No", "Yes"),
            bitfield.ValueField("Core clock sel", (30, 31)),
            ]

    class Feature(bitfield.Register):
        name = "Feature"
        fields = [
            bitfield.ValueField("IDCODE", (0, 31)),
            bitfield.ValueField("TRACEID", (32, 39)),
            bitfield.ValueField("I2C Addr", (40, 47)),
            bitfield.EnableField("Secpwd",  48),
            bitfield.EnableField("Deconly",  49),
            bitfield.EnableField("Pwdflash",  50),
            bitfield.EnableField("Pwdall",  51),
            bitfield.EnableField("Myassp",  52),
            bitfield.EnableField("Program",  53),
            bitfield.EnableField("Init",  54),
            bitfield.EnableField("Done",  55),
            bitfield.EnableField("Jtag",  56),
            bitfield.EnableField("Sspi",  57),
            bitfield.EnableField("I2c",  58),
            bitfield.EnableField("Mspi",  59),
            bitfield.EnableField("Boots1",  60),
            bitfield.EnableField("Boots2",  61),
            bitfield.EnableField("Rsvd",  62),
            ]

    IR_BYPASS               = 0xff
    IR_CLAMP                = 0x78
    IR_EXTEST               = 0x15
    IR_HIGHZ                = 0x18
    IR_IDCODE               = 0xe0
    IR_IDCODE_PRIV          = 0x16
    IR_ISC_ADDRESS_SHIFT    = 0x42
    IR_ISC_DATA_SHIFT       = 0x0a
    IR_ISC_DISABLE          = 0x26
    IR_ISC_DISCHARGE        = 0x14
    IR_ISC_ENABLE           = 0xc6
    IR_ISC_ERASE            = 0x0e
    IR_ISC_ERASE_DONE       = 0x24
    IR_ISC_NOOP             = 0x30
    IR_ISC_PROGRAM          = 0x67
    IR_ISC_PROGRAM_DONE     = 0x5e
    IR_ISC_PROGRAM_SECURITY = 0xce
    IR_ISC_PROGRAM_USERCODE = 0xc2
    IR_ISC_READ             = 0x80
    IR_LSC_ENABLE_X         = 0x74
    IR_LSC_RESET_CRC        = 0x3b
    IR_LSC_PROG_SED_CRC     = 0xa2
    IR_LSC_WRITE_BUS_ADDRESS= 0xf6
    IR_LSC_EBR_WRITE        = 0xb2
    IR_LSC_PCS_WRITE        = 0x72
    IR_LSC_WRITE_ADDRESS    = 0xb4
    IR_VERIFY_ID            = 0xe2
    IR_LSC_WRITE_COMP_DIC   = 0x02
    IR_LSC_INIT_ADDRESS     = 0x46
    IR_LSC_INIT_ADDRESS_UFM = 0x47
    IR_LSC_PROGRAM_SECPLUS  = 0xcf
    IR_LSC_PROG_INCR_RTI    = 0x82
    IR_LSC_VERIFY_INCR_RTI  = 0x6a
    IR_LSC_PROG_INCR_CMP    = 0xb8
    IR_LSC_PROG_INCR_NV     = 0x70
    IR_LSC_PROG_CTRL0       = 0x22
    IR_LSC_PROG_FEATURE     = 0xe4
    IR_LSC_READ_FEATURE     = 0xe7
    IR_LSC_PROG_FEABITS     = 0xf8
    IR_LSC_READ_FEABITS     = 0xfb
    IR_LSC_READ_PASSWORD    = 0xf2
    IR_LSC_READ_CTRL0       = 0x20
    IR_LSC_READ_STATUS      = 0x3c
    IR_LSC_READ_INCR_NV     = 0x73
    IR_LSC_CHECK_BUSY       = 0xf0
    IR_LSC_REFRESH          = 0x79
    IR_LSC_BITSTREAM_BURST  = 0x7a
    IR_LSC_UIDCODE_PUB      = 0x19
    IR_PRELOAD              = 0x1c
    IR_SAMPLE               = 0x1c
    IR_USERCODE             = 0xc0
    
    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        parts = [p for p in PARTS if int(port.idcode_at(index).drop_revision()) == p.idcode]
        if len(parts) > 1:
            suffixes = [p.name.split("-", 1)[1] for p in parts]
            prefix = parts[0].name.split("-", 1)[0]

            self.name = prefix + "-" + "/".join(suffixes)
        else:
            self.name = self.info.name
        self.info = parts[0]
        self.config_memory_size = self.info.row_count * self.info.col_bit_count // 8
        self.flash_size = (self.info.flash_page_count + self.info.ufm_page_count) * 16
        self.__bg_enable = None

    def start(self):
        self.uid = self.dr_shift(self.IR_LSC_UIDCODE_PUB, 0, 64)
        self.logger.info("UID: 0x%08x", self.uid)

        self._isc_enable(True)
        self.Status(self.status).dump(self.logger.info)
        self.Feature(self.feature).dump(self.logger.info)
        self._isc_disable()

        jtag.Tap.start(self)

    ERASE_SRAM = 1
    ERASE_FEATURE = 2
    ERASE_FLASH = 4
    ERASE_UFM = 8

    def _isc_enable(self, background = None):
        if self.__bg_enable is None and background is None:
            raise ValueError("Cannot reenable with no previous enable")
        if background is None:
            background = self.__bg_enable

        self.dr_shift(self.IR_ISC_DISABLE, None)
        self.wait_no_fail()
        self.dr_shift(self.IR_LSC_ENABLE_X if background else self.IR_ISC_ENABLE, 0x08, 8)
        self.wait_no_fail()
        self.__bg_enable = background

        self.status_check(0, 0x0200)

    def _isc_disable(self):
        self.dr_shift(self.IR_ISC_DISABLE, None)
        self.wait_no_fail()
        self.dr_shift(self.IR_BYPASS, None)
        self.__bg_enable = None

    def _erase(self, what):
        assert self.__bg_enable is not None
        self.dr_shift(self.IR_ISC_ERASE, what, 8)
        self.run(1)
        self.wait_no_fail()

    def _stop(self):
        self._erase(self.ERASE_SRAM)

    def stop(self):
        self._isc_enable(False)
        self._stop()
        self._isc_disable()

    def erase_all(self):
        self._isc_enable(False)
        self._erase(self.ERASE_SRAM | self.ERASE_UFM | self.ERASE_FLASH | self.ERASE_FEATURE)
        self._isc_disable()

    @property
    def status(self):
        return self.dr_shift(self.IR_LSC_READ_STATUS, 0, 32, read_tdo = True)

    @property
    def feature(self):
        return self.dr_shift(self.IR_LSC_READ_FEATURE, 0, 64, read_tdo = True)

    def status_check(self, expect_clear, expect_set):
        mask = expect_set | expect_clear
        assert self.status & mask == expect_set

    def wait_idle(self, timeout = 1.):
        step = .01

        for i in range(max(int(timeout / step), 1)):
            self.run(1)
            if self.dr_shift(self.IR_LSC_CHECK_BUSY, 0, 1, read_tdo = True) == 0:
                return
            time.sleep(.01)

        raise RuntimeError("Busy flag stuck")

    def wait_no_fail(self, timeout = 1.):
        self.wait_idle(timeout)
        self.status_check(3 << 12, 0)

    def _flash_erase(self):
        assert self.__bg_enable is not None
        self._erase(self.ERASE_FLASH)

    def _ufm_erase(self):
        assert self.__bg_enable is not None
        self._erase(self.ERASE_UFM)

    def _feature_erase(self):
        assert self.__bg_enable is not None
        self._erase(self.ERASE_FEATURE)

    def _flash_read(self, offset, size):
        return self._mem_read(offset, size, self.IR_LSC_INIT_ADDRESS, 0)

    def _ufm_read(self, offset, size):
        return self._mem_read(offset, size, self.IR_LSC_INIT_ADDRESS_UFM, 0x40000000)

    def _mem_read(self, offset, size, addr_init, offset_base):
        assert self.__bg_enable is not None
        self.status_check(0, 0xa00)

        self.dr_shift(addr_init, offset_base >> 28, 8)
        self.run(1)
        self.wait_no_fail()

        self.dr_shift(self.IR_LSC_WRITE_ADDRESS, offset_base + offset // 16, 32)
        self.run(1)
        self.wait_no_fail()

        cmds = [
            self.cmd_dr_shift(self.IR_LSC_READ_INCR_NV, None),
            self.run(10),
            self.cmd_dr_shift(None, None,
                            16 * 8,
                            read_tdo = True,
                            return_type = bytes),
            ]
        self.execute(cmds)

        data = b''
        for addr in range(offset & ~0xf, offset + size, 16):
            cmds = [
                self.cmd_dr_shift(self.IR_LSC_READ_INCR_NV, None),
                self.run(10),
                self.cmd_dr_shift(None, None,
                                16 * 8,
                                read_tdo = True,
                                return_type = bytes),
                ]
            self.execute(cmds)

            row_count = ((offset & 0xf) + size + 0xf) // 16
            data += cmds[2].tdo

        data = self.row_flip(data)

        return data[offset & 0xf : (offset & 0xf) + size]

    def _mem_write(self, offset, data, addr_init, offset_base):
        assert self.__bg_enable is not None
        self.status_check(0, 0x600)

        if offset % 16:
            prelen = (-offset % 16)
            self.logger.info("Pre len %d", prelen)
            data = b'\x00' * prelen + data
            offset = offset & ~0xf

        if len(data) % 16:
            postlen = (-len(data) % 16)
            self.logger.info("Post len %d", postlen)
            data += b'\x00' * postlen

        self.dr_shift(addr_init, 4, 8)
        self.run(1)
        self.wait_no_fail()

        self.dr_shift(self.IR_LSC_WRITE_ADDRESS, offset_base + offset // 16, 32)
        self.run(1)
        self.wait_no_fail()

        data = self.row_flip(data)

        for off in range(0, len(data), 16):
            self.execute([
                self.cmd_dr_shift(self.IR_LSC_PROG_INCR_NV, None),
                self.run(1),
                self.cmd_dr_shift(None, bytes(data[off : off+16]), read_tdo = False),
                self.run(1),
                ])
            assert not self.wait_no_fail()

    def _flash_write(self, offset, data):
        return self._mem_write(offset, data, self.IR_LSC_INIT_ADDRESS, 0)

    def _ufm_write(self, offset, data):
        return self._mem_write(offset, data, self.IR_LSC_INIT_ADDRESS_UFM, 0x40000000)

    def lol(self):
        assert self.__bg_enable is not None
        self.status_check(0, 0x600)

        #self.logger.info("Flash write 0x%08x %d", offset, len(data))
        if offset:# % 16:
            #prelen = (-offset % 16)
            prelen = offset
            self.logger.info("Pre len %d", prelen)
            data = b'\x00' * prelen + data
            #offset = offset & ~0xf
            offset = 0

        if len(data) % 16:
            postlen = (-len(data) % 16)
            self.logger.info("Post len %d", postlen)
            data += b'\x00' * postlen

        self.dr_shift(self.IR_LSC_INIT_ADDRESS, 4, 8)
        self.wait_no_fail()

        #self.dr_shift(self.IR_LSC_WRITE_ADDRESS, offset // 16, 32)
        #self.wait_no_fail()

        data = self.row_flip(data)

        for off in range(0, len(data), 16):
            self.dr_shift(self.IR_LSC_PROG_INCR_NV,
                          bytes(data[off : off+16]),
                          read_tdo = False)
            assert not self.wait_no_fail()

    def _flash_done_set(self):
        assert self.__bg_enable is not None
        self.dr_shift(self.IR_ISC_PROGRAM_DONE, None)
        self.run()

    def flash_erase(self):
        self._isc_enable(True)
        self._flash_erase()
        self._isc_disable()

    def ufm_erase(self):
        self._isc_enable(True)
        self._ufm_erase()
        self._isc_disable()

    def flash_read(self, offset, size):
        self._isc_enable(False)
        ret = self._flash_read(offset, size)
        self._isc_disable()
        return ret

    def ufm_read(self, offset, size):
        self._isc_enable(False)
        ret = self._ufm_read(offset, size)
        self._isc_disable()
        return ret

    def flash_write(self, offset, data):
        self._isc_enable(True)
        self._flash_write(offset, data)
        self._isc_disable()

    def ufm_write(self, offset, data):
        self._isc_enable(True)
        self._ufm_write(offset, data)
        self._isc_disable()

    def feature_read(self):
        self._isc_enable(True)
        ret = self.dr_shift(self.IR_LSC_READ_FEATURE, None, 64, read_tdo = True, return_type = bytes)
        self._isc_disable()
        return ret

    def feature_write(self, feature):
        self._isc_enable(True)

        self.dr_shift(self.IR_LSC_INIT_ADDRESS, 0x02, 8)
        self.run()

        self.dr_shift(self.IR_LSC_PROG_FEATURE, bytes(feature))
        self.run()

        self._isc_disable()

    @staticmethod
    def row_flip(data):
        assert len(data) % 16 == 0
        tmp = b""
        for offset in range(0, len(data), 16):
            tmp += bitswap8(data[offset : offset + 16])
        return tmp

    def reset(self):
        self._isc_enable(True)
        self.dr_shift(self.IR_ISC_PROGRAM_DONE, None)
        self.run()
        self.dr_shift(self.IR_LSC_REFRESH, None)
        self.run()
        self._isc_disable()



    ###
    ### Experimental
    ###

    def xsram_load(self, blob):
        st = self.status
        assert st & 0x00000040 == 0
        assert st & 0x00010000 == 0

        self.dr_shift(self.IR_LSC_REFRESH, None)
        self.dr_shift(self.IR_LSC_ENABLE_X, 0, 8)
        self.dr_shift(self.IR_LSC_INIT_ADDRESS, 1, 8)
        time.sleep(.001)
        self.dr_shift(self.IR_LSC_BITSTREAM_BURST, blob, len(blob) * 8)
        self.run(100)
        time.sleep(.01)
        self.dr_shift(self.IR_ISC_DISABLE, None)

        assert self.status & 0x00002100 == 0x00000100

    def sram_load(self, blob, usercode = 0):
        assert len(blob) == 135 * 333
        
        st = self.status
        assert st & 0x02000000 == 0
        assert st & 0x00008000 == 0

        self.dr_shift(self.IR_ISC_ENABLE, None)
        self.run(1000)

        self.dr_shift(self.IR_ISC_ERASE, 0x80, 8)
        self.run(1000)

        self.dr_shift(self.IR_LSC_PROG_CTRL0, 0x2, 32)
        self.run(1000)

        st = self.dr_shift(self.IR_LSC_READ_CTRL0, 0, 32, read_tdo = True)
        assert st == 0x2

        self.dr_shift(self.IR_LSC_INIT_ADDRESS, 0, 8)
        self.run(1000)
    
        for off in range(0, len(blob), 135):
            chunk = blob[off : off + 135]

            self.dr_shift(self.IR_LSC_PROG_INCR_RTI,
                          bitstring.BitString(chunk))
            self.run(1000)
        
        self.dr_shift(self.IR_ISC_PROGRAM_USERCODE, usercode, 32)
        self.run(1000)

        self.dr_shift(self.IR_ISC_DISABLE, None)
        self.run(10000)

        self.dr_shift(self.IR_BYPASS, None)
