import struct
from ... import bitstring
from ... import bitfield
from ...util.endian import swib_u16
from ...loadable.object import Program
from ...protocol import jtag
import datetime
from .series67 import Series67

class Series6(Series67):
    irlen = 6
    max_freq = 50e6

    def __init__(self, port, idcode):
        Series67.__init__(self, port, idcode)

    # JtagSramFpga
    USER_IR = [0x02, 0x03, 0x1a, 0x1b]
        
    ###
    ### Config port
    ###

    DNA_REGISTER = jtag.Dr(57)
    IR_ISC_DNA     = jtag.Instruction(0x30, "DNA_REGISTER")
    IR_ISC_NOP     = jtag.Instruction(0x14, "ISC_DEFAULT")

    IR_USER1 = jtag.Instruction(0x02, None)
    IR_USER2 = jtag.Instruction(0x03, None)
    IR_USER3 = jtag.Instruction(0x1a, None)
    IR_USER4 = jtag.Instruction(0x1b, None)

    IR_FUSE_READ   = jtag.Instruction(0x30, None) # between isc enable/disable
    IR_FUSE_UPDATE = jtag.Instruction(0x3a, None) # Update efuse to fpga
    IR_FUSE_OPTS   = jtag.Instruction(0x3c, None) # 16
    IR_FUSE_KEY    = jtag.Instruction(0x3b, None) # 256
    IR_FUSE_CNTL   = jtag.Instruction(0x34, None) # 32

    USER_CODE = jtag.Dr(32)
    IR_USERCODE = jtag.Instruction(0x08, "USER_CODE")

    @staticmethod
    def type1(op, addr, count):
        return [(1 << 13) | (op << 11) | (addr << 5) | count]

    @staticmethod
    def type2(op, count):
        return [(2 << 13), count >> 16, count & 0xffff]

    CFG_PREFIX = [0xaa99, 0x5566]

    CFG_STATUS = 0x8
    CFG_IDCODE = 0xe
    CFG_MASK   = 0x07
    CFG_CTL    = 0x06
    CFG_CBC_IV = 0x22
    CFG_CMD    = 0x05
    CFG_FRDI   = 0x03
    CFG_FRDO   = 0x04
    CFG_FLR    = 0x0d
    CFG_BOOTSTS= 0x20

    CFG_CMD_IPROG    = 0x0e

    @staticmethod
    def _cfg_conv_tdi(words):
        return struct.pack("<%dH" % len(words), *map(swib_u16, words))

    @staticmethod
    def _cfg_conv_tdo(data):
        return [swib_u16(x) for x in struct.unpack("<%dH" % (len(data) // 2), data)]

    @property
    def cfg_idcode(self):
        idcode = self.cfg_read(self.CFG_IDCODE, 2)
        return (idcode[0] << 16) | idcode[1]

    def dna_read(self):
        self.port.port.freq_cap("dna", 1e6)

        try:
            r = self.IR_ISC_DNA.cmd(read_tdo = True)

            self.execute([
                self.IR_ISC_ENABLE.cmd(),
                self.cmd_run(100),
                r,
                self.IR_ISC_DISABLE.cmd(),
            ])

            return r.tdo
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
            if target.startswith("xa6s"):
                target = target[2:]
            part_name = self.PART_NAMES.get(self.name, self.name)

            if not target.startswith(part_name):
                raise ValueError("Bitstream is for a %s, device is a %s (%s)" % (target, part_name, self.name))

        if expected_userid:
            # For no good reason, reading usercode at max speed does not work.
            # Whether this is because of crappy TCK/TDO routing or actual FPGA
            # thing, it still works when loading bitstream at full speed, so
            # we only want to reduce speed here, not when sending bitstream.
            with self.port.port.freq_capped("usercode", 15e6):
                userid = self.IR_USERCODE.shift(read_tdo = True)
            self.logger.debug("Current UserID=0x%08x", userid)

            if userid == expected_userid and not force_reload:
                self.logger.trace("UserID matches, doing nothing")
                return self.send_op_wait(-1, done = True)
            
        blob = program[0].data
        if len(blob) % 1:
            raise ValueError("Odd data length in bitstream")

        with self.logger.timed("Programming"):
            begin = datetime.datetime.now()

            ok = self.config_write(blob)

            # This is important, it enables internal CCLK
            self.run(10000)

            self.logger.debug("Status: %04x", self.cfg_status)
            self.cfg_status_dump()

            if not ok:
                raise RuntimeError("Unable to start FPGA")

        return self.send_op_wait(-1, done = True)

    def config_write(self, blob):
        prog_data = struct.unpack(">" + "H" * (len(blob) // 2), blob)

        self.logger.trace("Ready to load program, %d config words", len(prog_data))

        self.logger.trace("Resetting...")
        if not self.send_op_wait(self.IR_JPROGRAM, init = True):
            raise RuntimeError("Unable to reset FPGA")

        self.logger.trace("Loading program data...")

        self._cfg_shift(self.IR_CFG_IN, prog_data)
        self.run(40)

        self.logger.trace("Starting...")
        return self.send_op_wait(self.IR_JSTART, done = True)

    ###
    ### Status
    ###

    class Status(bitfield.Bitfield):
        SSWD           = bitfield.BooleanField(15)
        Suspend        = bitfield.BooleanField(14)
        InternalDone   = bitfield.BooleanField(13)
        InitB          = bitfield.BooleanField(12)
        Mode           = bitfield.Field(9, 3)
        Hswapen        = bitfield.BooleanField(8)
        PartSecured    = bitfield.BooleanField(7)
        Decerror       = bitfield.BooleanField(6)
        IOs            = bitfield.BinaryField(5, "High-Z", "As per config")
        GWE            = bitfield.BooleanField(4)
        GlobalTriState = bitfield.BooleanField(3)
        DCM            = bitfield.BooleanField(2)
        IDErr          = bitfield.BooleanField(1)
        CRCErr         = bitfield.BooleanField(0)

    class BootStatus(bitfield.Bitfield):
        StrikeCnt    = bitfield.Field(12, 4)
        CRC1Err      = bitfield.BooleanField(11)
        ID1Err       = bitfield.BooleanField(10)
        WTO1Err      = bitfield.BooleanField(9)
        Res1Err      = bitfield.BooleanField(8)
        Fallback1Err = bitfield.BooleanField(7)
        Valid1Err    = bitfield.BooleanField(6)
        CRC0Err      = bitfield.BooleanField(5)
        ID0Err       = bitfield.BooleanField(4)
        WTO0Err      = bitfield.BooleanField(3)
        Res0Err      = bitfield.BooleanField(2)
        Fallback0Err = bitfield.BooleanField(1)
        Valid0Err    = bitfield.BooleanField(0)
