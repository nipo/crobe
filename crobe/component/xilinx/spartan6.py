from ...part_id import PartId
from ...protocol import jtag
import struct
from ... import bitstring
from ...util.endian import swib_u16
import datetime
import os, os.path

parts = {
    0x04000093: "LX4",
    0x04001093: "LX9",
    0x04002093: "LX16",
    0x04004093: "LX25",
    0x04024093: "LX25T",
    0x04008093: "LX45",
    0x04028093: "LX45T",
    0x0400E093: "LX75",
    0x0402E093: "LX75T",
    0x04011093: "LX100",
    0x04031093: "LX100T",
    0x0401D093: "LX150",
    0x0403D093: "LX150T",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Spartan6(jtag.Tap):
    base_path = os.path.join(os.path.dirname(__file__), "fw")

    irlen = 6
    max_freq = 50e6

    config_memory_size = 500*1024

    IR_BYPASS      = 0x3f
    IR_ISC_ENABLE  = 0x10
    IR_ISC_PROGRAM = 0x11
    IR_ISC_DNA     = 0x30 # Doc says 0x31, iMPACT does 0x30
    IR_ISC_DISABLE = 0x16
    IR_JPROGRAM    = 0x0b
    IR_JSTART      = 0x0c
    IR_JSHUTDOWN   = 0x0d
    IR_CFG_IN      = 0x5
    IR_CFG_OUT     = 0x4

    IR_USER1 = 0x02
    IR_USER2 = 0x03
    IR_USER3 = 0x1a
    IR_USER4 = 0x1b

    IR_USERCODE = 0x08

    CFG_STATUS = 0x8
    CFG_IDCODE = 0xe

    IR_STATUS_ISC_DONE    = 0x04
    IR_STATUS_ISC_ENABLED = 0x08
    IR_STATUS_INIT        = 0x10
    IR_STATUS_DONE        = 0x20

    PART_NAMES = {
        "Spartan6-LX4": "6slx4",
        "Spartan6-LX9": "6slx9",
        "Spartan6-LX16": "6slx16",
        "Spartan6-LX25": "6slx25",
        "Spartan6-LX25T": "6slx25t",
        "Spartan6-LX45": "6slx45",
        "Spartan6-LX45T": "6slx45t",
        "Spartan6-LX75": "6slx75",
        "Spartan6-LX75T": "6slx75t",
        "Spartan6-LX100": "6slx100",
        "Spartan6-LX100T": "6slx100t",
        "Spartan6-LX150": "6slx150",
        "Spartan6-LX150T": "6slx150t",
    }

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = "Spartan6-" + parts[int(port.idcode_at(index).drop_revision())]

    def start(self):
        if not (self.ir_status & self.IR_STATUS_DONE):
            self.dna = self.dna_read()
            self.logger.info("Device DNA: %x", self.dna)
        else:
            self.logger.info("Device is running, cannot get DNA")
        jtag.Tap.start(self)

    @property
    def ir_status(self):
        return int(self.dr_shift(self.IR_BYPASS, None, read_ir = True))

    def send_op_wait(self, ir, expected):
        self.dr_shift(ir, None, read_tdo = False)

        for i in range(50):
            self.run(40)
            status = self.ir_status
            self.logger.info("IR status: 0x%02x", status)
            if status & expected:
                return True

        return False

    @property
    def cfg_idcode(self):
        idcode = self.cfg_read(self.CFG_IDCODE, 2)
        return (idcode[0] << 16) | idcode[1]

    def _cfg_shift(self, cmd, prog_data, read_rsp = False):
        blob = struct.pack("<" + "H" * len(prog_data), *map(swib_u16, prog_data))

        prog_dr = bitstring.BitString(blob)

        rsp = self.dr_shift(cmd, prog_dr, read_tdo = read_rsp)
        self.run(30)

        if read_rsp:
            return [swib_u16(x) for x in struct.unpack("<" + "H" * len(prog_data), rsp.data)]

    def cfg_read(self, reg, count):
        nop = 0x2000
        cmd = 0x2800 | (reg << 5) | count

        self._cfg_shift(self.IR_CFG_IN, [0xaa99, 0x5566, cmd, 0, 0])
        ret = self._cfg_shift(self.IR_CFG_OUT, [0] * count, True)
        self.dr_shift(self.IR_BYPASS, None)
        return ret

    @property
    def cfg_status(self):
        return self.cfg_read(self.CFG_STATUS, 1)[0]

    def dna_read(self):
        ops = [self.cmd_dr_shift(self.IR_ISC_ENABLE, None),
               self.cmd_run(20),
               self.cmd_dr_shift(self.IR_ISC_DNA, 0, 57),
               self.cmd_run(20),
               self.cmd_dr_shift(self.IR_ISC_DISABLE, None),
               ]

        self.execute(ops)

        return ops[2].tdo

    def stop(self):
        ops = [self.cmd_dr_shift(self.IR_ISC_ENABLE, None),
               self.cmd_run(20),
               self.cmd_dr_shift(self.IR_ISC_DISABLE, None),
               ]

        self.execute(ops)

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

    def config_write(self, blob):
        prog_data = struct.unpack(">" + "H" * (len(blob) // 2), blob)

        self.logger.info("Ready to load program, %d config words", len(prog_data))

        self.dr_shift(self.IR_ISC_ENABLE, None)
        self.run(20)

        self.logger.info("Resetting...")

        if not self.send_op_wait(self.IR_JPROGRAM, self.IR_STATUS_INIT):
            raise RuntimeError("Unable to reset FPGA")

        self.dr_shift(self.IR_JSHUTDOWN, None)

        self.logger.info("Loading program data...")

        self._cfg_shift(self.IR_CFG_IN, prog_data)
        self.run(40)

        self.logger.info("Starting...")

        self.dr_shift(self.IR_JSTART, None)
        self.run(20)

        self.dr_shift(self.IR_ISC_DISABLE, None)
        self.run(20)

        return self.send_op_wait(self.IR_BYPASS, self.IR_STATUS_DONE)

    def spi_interface(self):
        from ...loadable.object import Program
        filename = os.path.join(self.base_path, self.name.lower() + "_jtag_spi.bit.gz")
        self.load(Program.from_file(filename))

        from ..jtag_spi_bridge import JtagSpiBridge

        return JtagSpiBridge(self, self.IR_USER1, self.IR_USER2, 50e6)

    def child_spawn(self, mode = None):
        if mode == "spi":
            return self.spi_interface()
