from ...part_id import PartId
from ...protocol import jtag
import struct
from ... import bitstring
from ... import bitfield
from ...util.endian import swib_u32
import datetime
import os, os.path

parts = {
    0x03723093: "007",
    0x03722093: "010",
    0x0373c093: "012",
    0x03728093: "014",
    0x0373b093: "015",
    0x03727093: "020",
    0x0372c093: "030",
    0x03732093: "035",
    0x03731093: "045",
    0x03736093: "100",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Zynq(jtag.Tap):
    irlen = 6
    max_freq = 66e6

    config_memory_size = 4045564

    IR_BYPASS      = 0x3f
    IR_ISC_ENABLE  = 0x10
    IR_ISC_PROGRAM = 0x11
    IR_ISC_READ    = 0x15
    IR_ISC_NOP     = 0x14
    IR_ISC_DISABLE = 0x16
    IR_JPROGRAM    = 0x0b
    IR_JSTART      = 0x0c
    IR_JSHUTDOWN   = 0x0d
    IR_CFG_IN      = 0x05
    IR_CFG_OUT     = 0x04
    IR_XSC_DNA     = 0x17
    IR_PROGRAM_KEY = 0x12
    IR_FUSE_DNA    = 0x32
    IR_FUSE_CTS    = 0x30
    IR_USER1       = 0x02
    IR_USER2       = 0x03
    IR_USER3       = 0x22
    IR_USER4       = 0x23
    IR_USERCODE    = 0x08
    IR_IDCODE      = 0x09
    IR_XADC_DRP    = 0x27

    CFG_STATUS = 0x8
    CFG_IDCODE = 0xe

    ISC_DR_EN = 0x15

    IR_STATUS_ISC_DONE    = 0x04
    IR_STATUS_ISC_ENABLED = 0x08
    IR_STATUS_INIT        = 0x10
    IR_STATUS_DONE        = 0x20

    CTS_MAGIC_WRITE = 0xfeed28ac
    CTS_MAGIC_READ  = 0xa08a28ac

    class Efuse0(bitfield.Register):
        name = "Efuse0"
        fields = [
            bitfield.EnableField("Force PowerCycle Reconfig", 1),
            bitfield.DisableField("Key write", 2),
            bitfield.DisableField("AES Key read", 3),
            bitfield.DisableField("User Key read", 4),
            bitfield.DisableField("FUSE Control write", 5),
            bitfield.DisableField("Unsup 0", 6),
            bitfield.DisableField("Unsup 1", 7),
            bitfield.EnableField("AES Only", 8),
            bitfield.DisableField("JTAG", 9),
            bitfield.DisableField("BBRAM Key", 8),
            bitfield.EnableField("Force PowerCycle Reconfig (r)", 14+1),
            bitfield.DisableField("Key write (r)", 14+2),
            bitfield.DisableField("AES Key read (r)", 14+3),
            bitfield.DisableField("User Key read (r)", 14+4),
            bitfield.DisableField("FUSE Control write (r)", 14+5),
            bitfield.DisableField("Unsup 0 (r)", 14+6),
            bitfield.DisableField("Unsup 1 (r)", 14+7),
            bitfield.EnableField("AES Only (r)", 14+8),
            bitfield.DisableField("JTAG (r)", 14+9),
            bitfield.DisableField("BBRAM Key (r)", 14+8),
            ]

    class Efuse5(bitfield.Register):
        name = "Efuse5"
        fields = [
            bitfield.ValueField("DNA0", (8, 23)),
            bitfield.ValueField("DNA0 Ecc", (24, 29)),
            ]

    class Efuse6(bitfield.Register):
        name = "Efuse6"
        fields = [
            bitfield.ValueField("DNA1", (0, 23)),
            bitfield.ValueField("DNA1 Ecc", (24, 29)),
            ]
        
    class Efuse7(bitfield.Register):
        name = "Efuse7"
        fields = [
            bitfield.ValueField("DNA2", (0, 23)),
            bitfield.ValueField("DNA2 Ecc", (24, 29)),
            ]

    # Efuse 20-29: AES key (24 bit each + ECC)
    # Efuse 30:    USER[0] || AES key (8 + 16 bit + ECC)
    # Efuse 31:    USER[321] (24 bit + ECC)

    @staticmethod
    def efuse_ecc_update(value):
        value &= 0xc0ffffff
        for bit, mask in enumerate([0x03ff0f,
                                    0x1c78ee,
                                    0x64a6dd,
                                    0xa915bb,
                                    0xd20b77,
                                    0x1fffffff]):
            t = value & mask
            mask ^= mask >> 16
            mask ^= mask >> 8
            mask ^= mask >> 4
            mask ^= mask >> 2
            mask ^= mask >> 1
            mask &= 1
            value |= mask << (24 + bit)
        return value

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "Zynq-" + parts[int(port.idcode_at(index).drop_revision())]

    def stop(self):
        ops = [self.cmd_dr_shift(self.IR_JPROGRAM, None),
               self.cmd_dr_shift(self.IR_ISC_NOP, None),
               self.cmd_run(20),
               ]

        self.execute(ops)

    def start(self):
        self.dna = self.dna_read()
        self.logger.info("Device DNA: %x", self.dna)
        jtag.Tap.start(self)

    @property
    def ir_status(self):
        return int(self.dr_shift(self.IR_BYPASS, None, read_ir = True))

    def dna_read(self):
        ops = [self.cmd_dr_shift(self.IR_FUSE_DNA, 0, 64)]

        self.execute(ops)

        return ops[0].tdo

    @classmethod
    def cts_dr(cls, op = "read", row = 0, margin = 0, dma = 0, program = 1, bit = 0):
        assert 0 <= margin <= 2
        assert 0 <= row <= 0x1f
        assert 0 <= bit <= 0x1f
        assert op in ["read", "write"]

        cmd = (cls.CTS_MAGIC_READ if op == "read" else cls.CTS_MAGIC_WRITE) << 32
        cmd |= int(bool(program))
        cmd |= int(bool(dma)) << 1
        cmd |= row << 3
        cmd |= bit << 8
        cmd |= 1 << (13 + margin)
        return cmd

    def efuse_row_read(self, row, margin = 0):
        cts = self.cts_dr(op = "read", row = row, margin = margin)

        ops = [self.cmd_run(1),
               self.cmd_dr_shift(self.IR_FUSE_CTS, cts, 64, read_tdo = False),
               self.cmd_dr_shift(self.IR_FUSE_CTS, 0, 64, read_tdo = True),
               self.cmd_run(1),
               self.cmd_dr_shift(-1, None),
               ]
        self.execute(ops)

        value = ops[2].tdo >> 32

        return value

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
            cur = self.name[2:].lower()

            if not target.startswith(cur):
                raise ValueError("Bitstream is for a %s, device is a %s" % (target, cur))

        if expected_userid:
            userid = self.dr_shift(self.IR_USERCODE, 0, 32)
            self.logger.info("Current UserID=0x%08x", userid)
            if userid == expected_userid and not force_reload:
                self.logger.info("UserID matches, doing nothing")
                return
            
        blob = program[0].data
        if len(blob) % 1:
            raise ValueError("Odd data length in bitstream")

        begin = datetime.datetime.now()

        ok = self.config_write(blob)

        self.logger.info("Status: %04x", self.cfg_status)

        end = datetime.datetime.now()

        if not ok:
            raise RuntimeError("Unable to start FPGA")
        else:
            self.logger.info("Done OK, time taken: %s", end - begin)

    def send_op_wait(self, ir, expected):
        self.dr_shift(ir, None, read_tdo = False)

        for i in range(50):
            self.run(40)
            status = self.ir_status
            self.logger.info("IR status: 0x%02x", status)
            if status & expected:
                return True

        return False

    def _cfg_shift(self, cmd, prog_data, read_rsp = False):
        blob = struct.pack("<" + "L" * len(prog_data), *map(swib_u32, prog_data))

        prog_dr = bitstring.BitString(blob)

        rsp = self.dr_shift(cmd, prog_dr, read_tdo = read_rsp)
        self.run(30)

        if read_rsp:
            return [swib_u32(x) for x in struct.unpack("<" + "L" * len(prog_data), rsp.data)]

    def config_write(self, blob):
        prog_data = struct.unpack(">" + "L" * (len(blob) // 4), blob)

        self.logger.info("Ready to load program, %d config words", len(prog_data))

        self.logger.info("Resetting...")

        if not self.send_op_wait(self.IR_ISC_ENABLE, self.IR_STATUS_INIT):
            raise RuntimeError("Unable to reset FPGA")

        self.dr_shift(self.IR_ISC_NOP, None)
        self.run(20)

        self.logger.info("Loading program data...")

        self._cfg_shift(self.IR_CFG_IN, prog_data)
        self.run(100000)

        self.logger.info("Starting...")

        self.dr_shift(self.IR_JSTART, None)
        self.run(100)

        return self.send_op_wait(self.IR_BYPASS, self.IR_STATUS_DONE)

    def bbram_key_read(self):
        self.dr_shift(self.IR_ISC_ENABLE, self.ISC_DR_EN, 5)
        self.run(12)

        self.dr_shift(self.IR_ISC_READ, -1, 37)
        self.run(9)

        parts = []
        for i in range(8):
            r = self.dr_shift(self.IR_ISC_READ, -1, 37)
            self.run(9)
            part = r >> 5
            status = r & 0x1f
            self.logger.info("reading %08x" % part)
            parts.append(part)

        return struct.pack(">8L", *parts)

    def bbram_key_write(self, key):
        parts = struct.unpack(">8L", key)
        
        self.dr_shift(self.IR_ISC_ENABLE, self.ISC_DR_EN, 5)
        self.run(12)

        self.dr_shift(self.IR_PROGRAM_KEY, 0xffffffff, 32)
        self.run(9)
        self.dr_shift(self.IR_ISC_PROGRAM, 0xffffffff, 32)
        self.run(1)

        for part in parts:
            self.logger.info("writing %08x" % part)
            self.dr_shift(self.IR_ISC_PROGRAM, part, 32)
            self.run(1)

    def bbram_open(self):
        self.dr_shift(self.IR_JPROGRAM, None)
        self.dr_shift(self.IR_ISC_NOP, None)
        self.run(10000)

    def bbram_close(self):
        self.dr_shift(self.IR_ISC_DISABLE, None)
        self.run(12)
