from ...protocol import jtag
import struct
from ... import bitstring
import datetime

class Series67(jtag.Tap):
    irlen = 6
    max_freq = 50e6

    def __init__(self, port, index):
        jtag.Tap.__init__(self, port, index)

    IR_BYPASS      = 0x3f
    IR_ISC_ENABLE  = 0x10
    IR_ISC_PROGRAM = 0x11
    IR_ISC_DISABLE = 0x16
    IR_JPROGRAM    = 0x0b
    IR_JSTART      = 0x0c
    IR_JSHUTDOWN   = 0x0d
    IR_CFG_IN      = 0x5
    IR_CFG_OUT     = 0x4

    IR_STATUS_ISC_DONE    = 0x04
    IR_STATUS_ISC_ENABLED = 0x08
    IR_STATUS_INIT        = 0x10
    IR_STATUS_DONE        = 0x20

    OP_NOP = 0
    OP_READ = 1
    OP_WRITE = 2

    CFG_CMD_MFW      = 0x02
    CFG_CMD_START    = 0x05
    CFG_CMD_LFRM     = 0x03
    CFG_CMD_RCFG     = 0x04
    CFG_CMD_SHUTDOWN = 0x0b
    CFG_CMD_DESYNC   = 0x0d

    def cfg_read(self, reg, count):
        nop = self.type1(self.OP_NOP, 0, 0)
        cmd = self.type1(self.OP_READ, reg, count)

        self._cfg_shift(self.IR_CFG_IN, self.CFG_PREFIX + nop + cmd + nop + nop)
        ret = self._cfg_shift(self.IR_CFG_OUT, [0] * count, True)
        self.dr_shift(self.IR_BYPASS, None)
        return ret

    @property
    def cfg_status(self):
        return self.cfg_read(self.CFG_STATUS, 1)[0]

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

    @property
    def done(self):
        return bool(self.ir_status & self.IR_STATUS_DONE)
            
    def send_op_wait(self, ir, expected):
        self.dr_shift(ir, None, read_tdo = False)

        for i in range(50):
            self.run(40)
            status = self.ir_status
            self.logger.info("IR status: 0x%02x", status)
            if status & expected:
                return True

        return False

    @staticmethod
    def _cfg_conv_tdi(words):
        raise NotImplementedError()

    @staticmethod
    def _cfg_conv_tdo(data):
        raise NotImplementedError()

    def _cfg_shift(self, cmd, prog_data, read_rsp = False):
        blob = self._cfg_conv_tdi(prog_data)

        prog_dr = bitstring.BitString(blob)

        rsp = self.dr_shift(cmd, prog_dr, read_tdo = read_rsp)
        self.run(30)

        if read_rsp:
            return self._cfg_conv_tdo(bytes(rsp))

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
        ops = [self.cmd_dr_shift(self.IR_JPROGRAM, None),
               self.cmd_dr_shift(self.IR_ISC_NOP, None),
               self.cmd_run(20),
               ]

        self.execute(ops)

    ###
    ### Status
    ###

    @property
    def cfg_boot_status(self):
        return self.cfg_read(self.CFG_BOOTSTS, 1)[0]

    def cfg_status_dump(self):
        self.Status(self.cfg_status).dump(self.logger.info)
        self.BootStatus(self.cfg_boot_status).dump(self.logger.info)

