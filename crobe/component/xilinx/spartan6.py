from ...part_id import PartId
from ...adapter.protocol import jtag
import struct
from ... import bitstring
import datetime

parts = {
    0x04000093: "XC6SLX4",
    0x04001093: "XC6SLX9",
    0x04002093: "XC6SLX16",
    0x04004093: "XC6SLX25",
    0x04024093: "XC6SLX25T",
    0x04008093: "XC6SLX45",
    0x04028093: "XC6SLX45T",
    0x0400E093: "XC6SLX75",
    0x0402E093: "XC6SLX75T",
    0x04011093: "XC6SLX100",
    0x04031093: "XC6SLX100T",
    0x0401D093: "XC6SLX150",
    0x0403D093: "XC6SLX150T",
}

@jtag.Tap.db.register(*[PartId.from_idcode(c).drop_revision() for c in parts.keys()])
class Spartan6(jtag.Tap):
    irlen = 6

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

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)
        self.name = parts[int(port.idcode_at(index).drop_revision())]

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
        blob = struct.pack("<" + "H" * len(prog_data), *map(self.swib_u16, prog_data))

        prog_dr = bitstring.BitString(blob)

        rsp = self.dr_shift(cmd, prog_dr, read_tdo = read_rsp)
        self.run(30)

        if read_rsp:
            return [self.swib_u16(x) for x in struct.unpack("<" + "H" * len(prog_data), rsp.data)]

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

    def load(self, program):
        if len(program) != 1:
            raise ValueError("Bitstream programming only supports one config payload")

        if "device" in program.info:
            target = program.info["device"].lower()
            cur = self.name[2:].lower()

            if not target.startswith(cur):
                raise ValueError("Bitstream is for a %s, device is a %s" % (target, cur))

        blob = program[0].data
        if len(blob) % 1:
            raise ValueError("Odd data length in bitstream")

        begin = datetime.datetime.now()

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

        self.logger.info("Status: %04x", self.cfg_status)

        ok = self.send_op_wait(self.IR_BYPASS, self.IR_STATUS_DONE)

        end = datetime.datetime.now()

        if not ok:
            raise RuntimeError("Unable to start FPGA")
        else:
            self.logger.info("Done OK, time taken: %s", end - begin)
    
    @staticmethod
    def swib_u16(w):
        w = ((w & 0x5555) << 1) | ((w & 0xaaaa) >> 1)
        w = ((w & 0x3333) << 2) | ((w & 0xcccc) >> 2)
        w = ((w & 0x0f0f) << 4) | ((w & 0xf0f0) >> 4)
        w = ((w & 0x00ff) << 8) | ((w & 0xff00) >> 8)
        return w
        
