import struct
from ... import bitstring
from ... import bitfield
from ...protocol import jtag
from ...util.endian import swib_u32
from ...model import PortComponent
from ..model import SramFpga
import datetime
from .series67 import Series67
from ...protocol import spi

class Series7(Series67):
    irlen = 6
    max_freq = 50e6

    def __init__(self, port, index, idcode):
        Series67.__init__(self, port, index, idcode)

    # JtagSramFpga
    USER_IR = [0x02, 0x03, 0x22, 0x23]

    ###
    ### Config port
    ###

    USER_CODE = jtag.Dr(32)
    IR_USERCODE    = jtag.Instruction(0x08, "USER_CODE")
    ISC_READ_REG = jtag.Dr(37)
    IR_ISC_READ    = jtag.Instruction(0x15, "ISC_READ_REG")
    IR_ISC_NOP     = jtag.Instruction(0x14, None)
    IR_JSTART      = jtag.Instruction(0x0c, None)
    DNA_REGISTER = jtag.Dr(57)
    IR_XSC_DNA     = jtag.Instruction(0x17, "DNA_REGISTER")
    IR_PROGRAM_KEY = jtag.Instruction(0x12, "ISC_PROGRAM_REGISTER")

    class FuseDNA(bitfield.Bitfield):
        all          = bitfield.Field(0, 64)
        Unk0         = bitfield.Field(0, 2)
        ID1          = bitfield.Field(2, 7)
        ID2          = bitfield.Field(9, 7)
        ID0          = bitfield.Field(16, 5)
        Unk1         = bitfield.Field(21, 2)
        Code5        = bitfield.MappingField(23, 5, "0123456789ABCDEFGhjTlmnpqrUvwxYz")
        Code4        = bitfield.MappingField(28, 5, "0123456789ABCDEFGhjTlmnpqrUvwxYz")
        Code3        = bitfield.MappingField(33, 5, "0123456789ABCDEFGhjTlmnpqrUvwxYz")
        Code2        = bitfield.MappingField(38, 5, "0123456789ABCDEFGhjTlmnpqrUvwxYz")
        Code1        = bitfield.MappingField(43, 5, "0123456789ABCDEFGhjTlmnpqrUvwxYz")
        Code0        = bitfield.MappingField(48, 5, "0123456789ABCDEFGhjTlmnpqrUvwxYz")
        Unk2         = bitfield.Field(53, 11)

    FUSE_DNA_REGISTER = jtag.Dr(64, FuseDNA)
    IR_FUSE_DNA    = jtag.Instruction(0x32, "FUSE_DNA_REGISTER")
    FUSE_CMD_REGISTER = jtag.Dr(64)
    IR_FUSE_CTS    = jtag.Instruction(0x30, "FUSE_CMD_REGISTER")
    IR_FUSE_USER   = jtag.Instruction(0x33, None)
    IR_FUSE_KEY    = jtag.Instruction(0x31, None)
    IR_FUSE_CNTL   = jtag.Instruction(0x34, None)

    IR_USER1       = jtag.Instruction(0x02, None)
    IR_USER2       = jtag.Instruction(0x03, None)
    IR_USER3       = jtag.Instruction(0x22, None)
    IR_USER4       = jtag.Instruction(0x23, None)

    @staticmethod
    def type1(op, addr, count):
        return [(1 << 29) | (op << 27) | (addr << 13) | count]

    @staticmethod
    def type2(op, count):
        return [(2 << 29) | (op << 27) | count]

    CFG_PREFIX = [0xaa995566]

    CFG_STATUS = 0x07
    CFG_IDCODE = 0x0c
    CFG_MASK   = 0x06
    CFG_CTL0   = 0x05
    CFG_CTL1   = 0x18
    CFG_CBC_IV = 0x0b
    CFG_CMD    = 0x04
    CFG_FRDI   = 0x02
    CFG_FRDO   = 0x03
    CFG_DWC    = 0x1a
    CFG_CSOB   = 0x0f
    CFG_BOOTSTS= 0x16

    CFG_CMD_RCAP     = 0x06


    @staticmethod
    def _cfg_conv_tdi(words):
        return struct.pack("<%dL" % len(words), *map(swib_u32, words))

    @staticmethod
    def _cfg_conv_tdo(data):
        return [swib_u32(x) for x in struct.unpack("<%dL" % (len(data) // 4), data)]

    @property
    def cfg_idcode(self):
        return self.cfg_read(self.CFG_IDCODE, 1)[0]
    
    def dna_read(self):
        self.port.port.freq_cap("dna", 1e6)

        try:
            xsc_dna_read = self.IR_XSC_DNA.cmd(return_type = bitstring.BitString, read_tdo = True)
            fuse_dna_read = self.IR_FUSE_DNA.cmd(read_tdo = True)
            self.execute([self.IR_ISC_ENABLE.cmd(),
                          self.cmd_run(20),
                          xsc_dna_read,
                          fuse_dna_read,
                          self.cmd_run(20),
                          self.IR_ISC_DISABLE.cmd(),
            ])

            self.xsc_dna_value = xsc_dna_read.tdo
            self.fuse_dna = fuse_dna_read.tdo

            self.jtag_dna = "%s%s%s%s%s%s_%d_%d_%d" % (
                self.fuse_dna.Code0, self.fuse_dna.Code1,
                self.fuse_dna.Code2, self.fuse_dna.Code3,
                self.fuse_dna.Code4, self.fuse_dna.Code5,
                self.fuse_dna.ID0, self.fuse_dna.ID1,
                self.fuse_dna.ID2)
            self.logger.note("Fuse DNA: %s", self.fuse_dna)
            self.logger.note("XSC DNA: %s", self.xsc_dna_value)
            self.logger.note("JTAG DNA: %s", self.jtag_dna)

            return int(self.fuse_dna)
        finally:
            self.port.port.freq_cap("dna", None)

    def load(self, program, force_reload = False):
        if len(program) != 1:
            raise ValueError("Bitstream programming only supports one config payload")

        expected_userid = program.info.get("userid", None)
        if expected_userid == 0xffffffff:
            expected_userid = None

        if expected_userid:
            self.logger.trace("Expected UserID=0x%08x", expected_userid)
        
        if "device" in program.info:
            target = program.info["device"].lower()
            cur = self.name[2:].lower()

            #if not target.startswith(cur):
            #    raise ValueError("Bitstream is for a %s, device is a %s" % (target, cur))

        if expected_userid:
            userid = self.IR_USERCODE.shift()
            self.logger.note("Current UserID=0x%08x", userid)
            if userid == expected_userid and not force_reload:
                self.logger.info("UserID matches, doing nothing")
                return self.send_op_wait(-1, done = True)
            
        blob = program[0].data
        if len(blob) & 3:
            raise ValueError("Odd data length in bitstream")

        with self.logger.timed("Programming"):
            ok = self.config_write(blob)

            status = self.ir_status_read()
            self.logger.debug("IR Status: %04x", status)

            # This is important, it enables internal CCLK
            self.run(1000)

            if not ok:
                raise RuntimeError("Unable to start FPGA")

        return self.send_op_wait(-1, done = True)

    def config_write(self, blob):
        prog_data = struct.unpack(">" + "L" * (len(blob) // 4), blob)

        self.logger.trace("Ready to load program of %d config words", len(prog_data))

        self.logger.trace("Resetting...")
        self.IR_JPROGRAM.shift()
        self.run(20)

        self.IR_ISC_NOP.shift()
        self.run(20)

        self.logger.trace("CFG IDCODE: %08x", self.cfg_idcode)
        self.cfg_status_dump()

        self.logger.trace("Loading program data...")
        self._cfg_shift(self.IR_CFG_IN, prog_data)
        self.run(100000)

        self.logger.trace("Loading done...")
        self.cfg_status_dump()

        self.logger.trace("Starting...")
        self.IR_JSTART.shift()
        self.run(10000)
        self.IR_BYPASS.shift()
        self.run(10000)
        self.logger.trace("Start done...")

        self.cfg_status_dump()

        return self.send_op_wait(-1, done = True)

    ###
    ### Status
    ###

    class Status(bitfield.Bitfield):
        all          = bitfield.Field(0, 32)
        Res31        = bitfield.BooleanField(31)
        CfgBvs       = bitfield.BooleanField(30)
        BadPktError  = bitfield.BooleanField(29)
        PudcB        = bitfield.BooleanField(28)
        HMacError    = bitfield.BooleanField(27)
        BusWidth     = bitfield.MappingField(25, 2, {0:"1",1:"8",2:"16",3:"32"})
        Res21        = bitfield.Field(21, 4)
        StartupPhase = bitfield.GrayField(18, 3)
        SecurityError= bitfield.BooleanField(16)
        IDCodeError  = bitfield.BooleanField(15)
        Done         = bitfield.BooleanField(14)
        DoneInt      = bitfield.BooleanField(13)
        InitB        = bitfield.BooleanField(12)
        InitBInt     = bitfield.BooleanField(11)
        Mode         = bitfield.Field(8, 3)
        GHIGH_B      = bitfield.BooleanField(7)
        GWE          = bitfield.BooleanField(6)
        GTSCfgB      = bitfield.BooleanField(5)
        EOSReached   = bitfield.BooleanField(4)
        DCIMatch     = bitfield.BooleanField(3)
        PLLLock      = bitfield.BooleanField(2)
        DecryptEn    = bitfield.BooleanField(1)
        CRC          = bitfield.BinaryField(0, "OK", "error")

    class BootStatus(bitfield.Bitfield):
        all          = bitfield.Field(0, 32)
        Res          = bitfield.Field(16, 16)
        HMAC1Err     = bitfield.BinaryField(15, "OK", "error")
        Wrap1Err     = bitfield.BinaryField(14, "OK", "error")
        CRC1Err      = bitfield.BinaryField(13, "OK", "error")
        ID1Err       = bitfield.BinaryField(12, "OK", "error")
        WTO1Err      = bitfield.BinaryField(11, "OK", "error")
        IProg1Err    = bitfield.BinaryField(10, "OK", "error")
        Fallback1Err = bitfield.BinaryField(9, "OK", "error")
        Valid1Err    = bitfield.BinaryField(8, "OK", "error")
        HMAC0Err     = bitfield.BinaryField(7, "OK", "error")
        Wrap0Err     = bitfield.BinaryField(6, "OK", "error")
        CRC0Err      = bitfield.BinaryField(5, "OK", "error")
        ID0Err       = bitfield.BinaryField(4, "OK", "error")
        WTO0Err      = bitfield.BinaryField(3, "OK", "error")
        IProg0Err    = bitfield.BinaryField(2, "OK", "error")
        Fallback0Err = bitfield.BinaryField(1, "OK", "error")
        Valid0Err    = bitfield.BinaryField(0, "OK", "error")

    ###
    ### EFUSE
    ###

    FUSE_CFG_KEY_PROTECT_WRITE = 2
    FUSE_CFG_KEY_PROTECT_READ = 3
    FUSE_CFG_USER_PROTECT_READ = 4

    class Efuse5(bitfield.Bitfield):
        all = bitfield.Field(0, 32)
        DNA15_0 = bitfield.Field(8, 16)
        Ecc = bitfield.Field(24, 6)

    class Efuse6(bitfield.Bitfield):
        all = bitfield.Field(0, 32)
        DNA40_16 = bitfield.Field(0, 24)
        Ecc = bitfield.Field(24, 6)
        
    class Efuse7(bitfield.Bitfield):
        all = bitfield.Field(0, 32)
        DNA64_41 = bitfield.Field(0, 24)
        Ecc = bitfield.Field(24, 6)

    # Efuse 20-29: AES key (24 bit each + ECC)
    # Efuse 30:    USER[0] || AES key (8 + 16 bit + ECC)
    # Efuse 31:    USER[321] (24 bit + ECC)

    @staticmethod
    def efuse_ecc_update_old(value):
        value &= 0xc0ffffff
        for bit, mask in enumerate([0x0003ff0f,
                                    0x001c78ee,
                                    0x0064a6dd,
                                    0x00a915bb,
                                    0x00d20b77,
                                    0x1fffffff]):
            t = value & mask
            t ^= t >> 16
            t ^= t >> 8
            t ^= t >> 4
            t ^= t >> 2
            t ^= t >> 1
            t &= 1
            value |= t << (24 + bit)
        return value

    @staticmethod
    def efuse_ecc_update_new(value):
        ecc = 0
        p = 0
        for i, v in enumerate([
            0x1d, 0x1b, 0x17, 0x0f, 0x1c, 0x1a, 0x16, 0x0e,
            0x19, 0x15, 0x0d, 0x13, 0x0b, 0x07, 0x03, 0x05,
            0x09, 0x11, 0x06, 0x0a, 0x12, 0x0c, 0x14, 0x18,
            ]):
            if (value >> i) & 1:
                ecc ^= v
                p ^= 1
        for i in range(5):
            if (ecc >> i) & 1:
                p ^= 1
        return (value & 0xc0ffffff) | (ecc << 24) | (p << 29)

    @classmethod
    def efuse_ecc_update(cls, value):
        a = cls.efuse_ecc_update_old(value)
        b = cls.efuse_ecc_update_new(value)
        assert a == b
        return a

    class FuseCts(bitfield.Bitfield):
        KEY = 0xa08a28ac

        dma = bitfield.BooleanField(0)
        program = bitfield.BooleanField(1)
        data = bitfield.Field(32, 32)
        row = bitfield.Field(3, 5)
        bit = bitfield.Field(8, 5)
        margin_opt = bitfield.Field(13, 2)

    @classmethod
    def dr_cts_write(cls, row, bit, margin_opt, program, dma):
        assert 0 <= margin_opt <= 3
        assert 0 <= row <= 0x1f
        assert 0 <= bit <= 0x1f

        cmd = 0xa08a28ac << 32
        cmd |= int(bool(dma))
        cmd |= int(bool(program)) << 1
        cmd |= row << 3
        cmd |= bit << 8
        cmd |= margin_opt << 13
        return cmd

    def efuse_row_read(self, row, margin_opt = 0):
        """
        From xilskey_jscmd's JtagRead function:

        - Go to TLR to clear FUSE_CTS
        - Load FUSE_CTS instruction on IR
        - Step to CDR/SDR to shift in 32-bits FUSE_CTS command word
          a_row<4:0>;  dma=1;  pgm=0; tp_sel<1:0>; ecc_dma
          Shift in MAGIC_CTS_WRITE "A08A28AC"
        - Step to E1DR/UDR to update FUSE_CTS reg
        - Step to SDS/CDR/SDR to shift out captured row
          while shifting in a new command with next row
          address w/ or w/o new tp_sel or ecc_dma setting
        - Captured macro word (32 bits) is stored in jtag_dr[63:32]
        - If ecc_dma = 1, jtag_dr[61:32] = {DED check-sum, SEC syndrome, decoded payload}

        Except we do not go through TLR because it causes problems
        with other TAPs. Instead, shift FUSE_CTS with zeroes.
        """
        cts = self.FuseCts(row = row, bit = 0, margin_opt = margin_opt,
                           program = 0, dma = 1, data = self.FuseCts.KEY)

        ops = [self.IR_FUSE_CTS.cmd(0),
               self.cmd_run(12),
               self.IR_FUSE_CTS.cmd(cts, read_tdo = False),
               self.IR_FUSE_CTS.cmd(read_tdo = True),
               self.cmd_run(1),
               self.BYPASS.cmd(),
               ]
        self.execute(ops)

        value = (ops[3].tdo.data) & 0x3fffffff

        return value

    def cmd_efuse_bit_set(self, row, bit):
        """
        From xilskey_jscmd's JtagWrite function:
        
        - Go to TLR to clear FUSE_CTS
        - Load FUSE_CTS instruction on IR
        - Step to CDR/SDR to shift in the command word
          dma=1; pgm=1; a_row<4:0> & a_bit<4:0>
          (Continuously shift in MAGIC_CTS_WRITE)
        - Loop back to E1DR/UDR/SDS/CDR/E1DR/UDR
        - Go to RTI and stay in RTI EXACTLY Tpgm = 12 us (tbd) and immediately exit to SDS
        - Go to TLR to clear FUSE_CTS

        Except we do not go through TLR because it causes problems
        with other TAPs. Instead, shift FUSE_CTS with zeroes.
        """
        cts = self.dr_cts_write(row = row, bit = bit, margin_opt = 0, program = 1, dma = 1)
        cts = self.FuseCts(row = row, bit = bit, margin_opt = 0,
                           program = 1, dma = 1, data = self.FuseCts.KEY)

        return [self.IR_FUSE_CTS.cmd(0),
                self.cmd_run(1),
                self.IR_FUSE_CTS.cmd(cts),
                self.IR_FUSE_CTS.cmd(None),
                self.cmd_run(int(self.port.port.freq * 12e-6) or 1),
                self.IR_FUSE_CTS.cmd(0),
                self.BYPASS.cmd(),
                self.cmd_run(1),
                ]

    def efuse_cfg_set(self, bit):
        self.execute(self.cmd_efuse_bit_set(0, bit)
                     + self.cmd_efuse_bit_set(0, 14 + bit))

    def efuse_bit_set(self, row, bit):
        self.execute(self.cmd_efuse_bit_set(row, bit))

    def cmd_efuse_row_set(self, row, value):
        ret = []
        for i in range(32):
            if (value >> i) & 1:
                ret += self.cmd_efuse_bit_set(row, i)
        return ret

    def efuse_key_write(self, key):
        key = int.from_bytes(key, "big")
        cmds = []
        for i in range(11):
            chunk = (key >> (24 * i)) & 0xffffff
            data = self.efuse_ecc_update(chunk)
            cmds += self.cmd_efuse_row_set(20 + i, data)
        self.execute(cmds)

    def efuse_key_read(self):
        ret = 0
        self.efuse_row_read(20)
        for i in range(11):
            row = self.efuse_row_read(20 + i)
            row &= 0xffffff
            ret |= row << (24 * i)
        ret &= (1 << 256) - 1
        return ret.to_bytes(32, "big")

    def efuse_key_ecc_valid(self):
        ret = 0
        self.efuse_row_read(20)
        for i in range(11):
            row = self.efuse_row_read(20 + i)
            if self.efuse_ecc_update(row) != row:
                return False
        return True
    
    ###
    ### BBRAM
    ###

    ISC_DR_EN = 0x15

    def bbram_key_read(self):
        cmds = [
            self.IR_ISC_ENABLE.cmd(self.ISC_DR_EN),
            self.cmd_run(12),
            self.IR_ISC_READ.cmd(-1),
            self.cmd_run(9),
            ]

        parts = []
        for i in range(8):
            r = self.IR_ISC_READ.cmd(-1, read_tdo = True)
            parts.append(r)
            cmds += [
                r,
                self.cmd_run(9),
                ]
        self.execute(cmds)

        d = []
        for i, p in enumerate(parts):
            part = p.tdo >> 5
            status = p.tdo & 0x1f
            self.logger.debug("bbram[%d] 0x%08x" % (i, part))
            d.append(part)

        return struct.pack(">8L", *d)

    def bbram_key_write(self, key):
        parts = struct.unpack(">8L", key)

        cmds = [
            self.IR_ISC_ENABLE.cmd(self.ISC_DR_EN),
            self.cmd_run(12),
            self.IR_PROGRAM_KEY.cmd(-1),
            self.cmd_run(9),
            self.IR_ISC_PROGRAM.cmd(-1),
            self.cmd_run(1),
        ]

        for part in parts:
            cmds += [
                self.IR_ISC_PROGRAM.cmd(part),
                self.cmd_run(1),
                ]
        self.execute(cmds)

    def bbram_open(self):
        self.execute([
            self.IR_JPROGRAM.cmd(),
            self.IR_ISC_NOP.cmd(),
            self.cmd_run(10000),
            ])

    def bbram_close(self):
        self.execute([
            self.IR_ISC_DISABLE.cmd(),
            self.cmd_run(12),
            ])

@spi.Target.db.register("series7_slave")
def series7_slave_probe(target, *args):
    return Series7SlaveSerial(target)

class Series7SlaveSerial(PortComponent, SramFpga):
    def __init__(self, port):
        PortComponent.__init__(self, port, "Slave Series7")
        SramFpga.__init__(self)

    def start(self):
        self.port.freq_cap("series7", 50e6)
        super().start()

    def stop(self):
        pass

    def reset(self):
        pass

    def load(self, program):
        self.port.port.reset(True)
        self.port.port.reset(False)

        blob = program[0].data
        self.logger.trace("Loading %d bytes bitstream", len(blob))
        self.port.execute([self.port.cmd_cs(True)])
        for off in range(0, len(blob), 1024):
            chunk = blob[off : off + 1024]
            self.port.execute([self.port.cmd_shift(chunk, read_miso = False)])
        self.port.execute([self.port.cmd_shift(b'\x00'*32, read_miso = False)])
        self.port.execute([self.port.cmd_cs(False)])
