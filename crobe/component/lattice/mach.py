from ...part_id import PartId
from ...protocol import jtag
from ... import bitfield
from ...util.endian import bitswap8
import struct
from ... import bitstring
import datetime
import time

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

        self.uid = self.dr_shift(self.IR_LSC_UIDCODE_PUB, 0, 64)
        self.logger.info("UID: 0x%08x", self.uid)

        self.Status(self.status).dump(self.logger.info)
        self.Feature(self.feature).dump(self.logger.info)

    def stop(self):

        self.dr_shift(self.IR_ISC_ENABLE, 0, 8)
        self.run()

        self.dr_shift(self.IR_ISC_ERASE, 0xf, 8)
        self.run()
        self.wait_idle()

        self.dr_shift(self.IR_ISC_DISABLE, 0, 8)
        self.run()

    def status_check(self, expect_clear, expect_set):
        mask = expect_set | expect_clear
        assert self.status & mask == expect_set

    def config_write(self, program):
        bs = MachXOBitstream(program)
        assert bs.info.idcode == self.info.idcode
        assert self.info.row_count == len(bs.rti)

        self.status_check(0x00010040, 0)

        self.dr_shift(self.IR_ISC_ENABLE, 0, 8)
        self.run()

        self.dr_shift(self.IR_ISC_ERASE, 0xf, 8)
        self.run()
        self.wait_idle()

        self.dr_shift(self.IR_LSC_PROG_CTRL0, 0x40000000, 32)
        self.run()
        self.dr_shift(self.IR_LSC_INIT_ADDRESS, 0, 8)
        self.run()
        time.sleep(.001)

        for frame in bs.rti:
            data = bitstring.BitString(bytes(frame.data))
            self.dr_shift(self.IR_LSC_PROG_INCR_RTI, data)
            self.run()
        self.run(1024)
        self.usercode_program(0)

        self.dr_shift(self.IR_ISC_PROGRAM_DONE, None)
        self.run()
        self.run(1024)
        self.dr_shift(self.IR_ISC_DISABLE, None)
        self.run()
        
        self.status_check(0x00002000, 0x00000100)

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

    def wait_idle(self, timeout = 1.):
        step = .01

        for i in range(max(int(timeout / step), 1)):
            if self.dr_shift(self.IR_LSC_CHECK_BUSY, 0, 1, read_tdo = True) == 0:
                return
            time.sleep(.01)

        raise RuntimeError("Busy flag stuck")

    def blob_push(self, blob, chunk_size, ir):
        for off in range(0, len(blob), chunk_size):
            chunk = blob[off : off + chunk_size].ljust(chunk_size, b'\x00')

            self.dr_shift(ir, bitstring.BitString(chunk))
            self.run(2)
            self.wait_idle()

    def cfg_program(self, blob):
        self.dr_shift(self.IR_LSC_INIT_ADDRESS, 0x4, 8)
        self.run(2)

        self.blob_push(blob, 16, self.IR_LSC_PROG_INCR_NV)

    def ufm_program(self, blob):
        self.dr_shift(self.IR_LSC_INIT_ADDRESS_UFM, None)
        self.run(2)

        self.blob_push(blob, 16, self.IR_LSC_PROG_INCR_NV)

    def usercode_program(self, usercode):
        self.dr_shift(self.IR_USERCODE, usercode, 32)
        self.run()
        self.dr_shift(self.IR_ISC_PROGRAM_USERCODE, None)
        self.run(2)

    def feature_program(self, feature, feabits):
        self.dr_shift(self.IR_LSC_INIT_ADDRESS, 0x02, 8)
        self.run()

        self.feature = feature
        self.wait_idle()
        assert self.feature == feature
        self.feabits = feabits
        self.wait_idle()
        assert self.feabits & 0xfff2 == feabits

    @property
    def status(self):
        return self.dr_shift(self.IR_LSC_READ_STATUS, 0, 32, read_tdo = True)

    @property
    def feature(self):
        return self.dr_shift(self.IR_LSC_READ_FEATURE, 0, 64, read_tdo = True)

    @feature.setter
    def feature(self, value):
        self.dr_shift(self.IR_LSC_PROG_FEATURE, value, 64)
        self.run()

    @property
    def feabits(self):
        return self.dr_shift(self.IR_LSC_READ_FEABITS, 0, 16, read_tdo = True)

    @feabits.setter
    def feabits(self, value):
        self.dr_shift(self.IR_LSC_PROG_FEABITS, value, 16)
        self.run()

    def internal_flash_load(self, cfg, ufm, usercode, feature, feabits):
        st = self.status
        assert st & 0x02000000 == 0
        assert st & 0x00008000 == 0

        self.dr_shift(self.IR_ISC_ENABLE, None)
        self.run(2)

        self.dr_shift(self.IR_ISC_ERASE, 0x70, 8)
        self.wait_idle()

        st = self.status
        assert st & 0x0000c000 == 0

        self.cfg_program(cfg)
        self.ufm_program(ufm)
        self.usercode_program(usercode)
        
        st = self.status
        assert st & 0x0000c000 == 0

        self.feature_program(feature, feabits)

        self.dr_shift(self.IR_ISC_PROGRAM_DONE, None)
        self.run(2)
        self.wait_idle()

        self.dr_shift(self.IR_ISC_DISABLE, None)
        self.run(2)

        self.dr_shift(self.IR_BYPASS, None)
