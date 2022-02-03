import struct
from ... import bitstring
from ... import bitfield
from ...util.endian import swib_u16
from ...loadable.object import Program
import datetime
from .series67 import Series67

class Series6(Series67):
    irlen = 6
    max_freq = 50e6

    def __init__(self, port, index, idcode):
        Series67.__init__(self, port, index, idcode)

    # JtagSramFpga
    USER_IR = [0x02, 0x03, 0x1a, 0x1b]
        
    ###
    ### Config port
    ###

    IR_BYPASS      = 0x3f
    IR_ISC_DNA     = 0x30 # Doc says 0x31, iMPACT does 0x30
    IR_ISC_NOP     = 0x14

    IR_USER1 = 0x02
    IR_USER2 = 0x03
    IR_USER3 = 0x1a
    IR_USER4 = 0x1b

    IR_FUSE_READ   = 0x30 # between isc enable/disable
    IR_FUSE_UPDATE = 0x3a # Update efuse to fpga
    IR_FUSE_OPTS   = 0x3c # 16
    IR_FUSE_KEY    = 0x3b # 256
    IR_FUSE_CNTL   = 0x34 # 32

    IR_USERCODE = 0x08

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
        ops = [self.cmd_dr_shift(self.IR_ISC_ENABLE, None),
               self.cmd_run(20),
               self.cmd_dr_shift(self.IR_ISC_DNA, 0, 57),
               self.cmd_run(20),
               self.cmd_dr_shift(self.IR_ISC_DISABLE, None),
               ]

        self.execute(ops)

        return ops[2].tdo

    def load(self, program, force_reload = False):
        if len(program) != 1:
            raise ValueError("Bitstream programming only supports one config payload")

        expected_userid = program.info.get("userid", None)
        if expected_userid == 0xffffffff:
            expected_userid = None

        if expected_userid:
            self.logger.info("Expected UserID=0x%08x", expected_userid)
        
        if "device" in program.info:
            target = program.info["device"].lower()
            part_name = self.PART_NAMES.get(self.name, self.name)

            if not target.startswith(part_name):
                raise ValueError("Bitstream is for a %s, device is a %s (%s)" % (target, part_name, self.name))

        if expected_userid:
            # For no good reason, reading usercode at max speed does not work.
            # Whether this is because of crappy TCK/TDO routing or actual FPGA
            # thing, it still works when loading bitstream at full speed, so
            # we only want to reduce speed here, not when sending bitstream.
            intf = self.port.port
            intf.freq_cap("usercode", 15e6)

            userid = self.dr_shift(self.IR_USERCODE, 0, 32)
            self.logger.info("Current UserID=0x%08x", userid)
            intf.freq_cap("test", None)

            if userid == expected_userid and not force_reload:
                self.logger.info("UserID matches, doing nothing")
                return self.send_op_wait(-1, self.IR_STATUS_DONE)
            
        blob = program[0].data
        if len(blob) % 1:
            raise ValueError("Odd data length in bitstream")

        begin = datetime.datetime.now()

        ok = self.config_write(blob)

        # This is important, it enables internal CCLK
        self.run(10000)

        self.logger.info("Status: %04x", self.cfg_status)
        self.cfg_status_dump()

        end = datetime.datetime.now()

        if not ok:
            raise RuntimeError("Unable to start FPGA")
        else:
            self.logger.info("Done OK, time taken: %s", end - begin)

        return self.send_op_wait(-1, self.IR_STATUS_DONE)

    def config_write(self, blob):
        prog_data = struct.unpack(">" + "H" * (len(blob) // 2), blob)

        self.logger.info("Ready to load program, %d config words", len(prog_data))

        self.logger.info("Resetting...")
        if not self.send_op_wait(self.IR_JPROGRAM, self.IR_STATUS_INIT):
            raise RuntimeError("Unable to reset FPGA")

        self.logger.info("Loading program data...")

        self._cfg_shift(self.IR_CFG_IN, prog_data)
        self.run(40)

        self.logger.info("Starting...")
        return self.send_op_wait(self.IR_JSTART, self.IR_STATUS_DONE)

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
