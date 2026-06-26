from ...protocol import jtag
import struct
from ... import db
from ... import bitstring
from ...bitfield import *
from ..model import JtagSramFpga
import datetime

class Series67(jtag.Tap, JtagSramFpga):
    irlen = 6
    max_freq = 50e6

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        JtagSramFpga.__init__(self)
        self.__can_stop = False

    ISC_DEFAULT     = jtag.Dr(1)
    CONFIG          = jtag.Dr(None)
    DEVICE_ID       = jtag.Dr(32)

    IR_BYPASS      = jtag.Instruction(0x3f, "BYPASS_REG")

    IDCODE       = jtag.Instruction(0x09, "DEVICE_ID")

    BOUNDARY = jtag.Dr(None)
    SAMPLE       = jtag.Instruction(0x01, "BOUNDARY")

    ISC_ENABLE_REGISTER  = jtag.Dr(5)
    IR_ISC_ENABLE  = jtag.Instruction(0x10, "ISC_ENABLE_REGISTER")
    ISC_PROGRAM_REGISTER  = jtag.Dr(32)
    IR_ISC_PROGRAM = jtag.Instruction(0x11, "ISC_PROGRAM_REGISTER")
    IR_ISC_DISABLE = jtag.Instruction(0x16, "ISC_DEFAULT")
    IR_JPROGRAM    = jtag.Instruction(0x0b, "ISC_DEFAULT")
    IR_JSTART      = jtag.Instruction(0x0c, "ISC_DEFAULT")
    IR_JSHUTDOWN   = jtag.Instruction(0x0d, "ISC_DEFAULT")
    IR_CFG_IN      = jtag.Instruction(0x5, "CONFIG")
    IR_CFG_OUT     = jtag.Instruction(0x4, "CONFIG")

    class IrStatus(Bitfield):
        isc_done = BooleanField(2)
        isc_enabled = BooleanField(3)
        init = BooleanField(4)
        done = BooleanField(5)
    
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
        self.BYPASS.shift()
        return ret

    def cfg_cmd(self, cmd):
        nop = self.type1(self.OP_NOP, 0, 0)
        cmd_write = self.type1(self.OP_WRITE, self.CFG_CMD, 1)

        self._cfg_shift(self.IR_CFG_IN, self.CFG_PREFIX + nop + cmd_write + [cmd] + nop)
        self.BYPASS.shift()

    @property
    def cfg_status(self):
        return self.cfg_read(self.CFG_STATUS, 1)[0]

    def option_set(self, opt):
        if opt == "can_stop":
            self.__can_stop = True
            return
        super().option_set(opt)

    def start(self):
        self.logger.note("Our IDCODE: 0x%08x", self.IDCODE.shift(read_tdo = True))
        self.cfg_status_dump()
            
        if not self.__can_stop and self.done:
            self.logger.warning("Device is running, cannot get DNA")
        else:
            self.stop()
            self.dna = self.dna_read()
            self.logger.note("Device DNA: %x", self.dna)
        jtag.Tap.start(self)

    @property
    def done(self):
        return self.ir_status_read().done
            
    def send_op_wait(self, ir, **expected):
        if isinstance(ir, jtag.TapInstruction):
            ir = ir.ir
        self.dr_shift(ir, None, read_tdo = False)

        for i in range(50):
            self.run(40)
            status = self.ir_status_read()
            self.logger.debug("IR status: %s", status)
            ok = all(getattr(status, k) == v for (k, v) in expected.items())
            if ok:
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

        if isinstance(cmd, jtag.TapInstruction):
            cmd = cmd.ir
        shift = self.cmd_dr_shift(cmd, prog_dr, read_tdo = read_rsp)

        self.execute([
            shift,
            self.cmd_run(30),
        ])
        
        if read_rsp:
            return self._cfg_conv_tdo(bytes(shift.tdo))

    def stop(self):
        ops = [self.IR_JPROGRAM.cmd(),
               self.IR_ISC_NOP.cmd(),
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
        cs = self.Status(self.cfg_status)
        cbs = self.BootStatus(self.cfg_boot_status)
        self.logger.note("Config status %r %08x", cs, cs.all)
        self.logger.note("Config boot status %r %08x", cbs, cbs.all)

    def reset(self):
        #self.cfg_cmd(self.CFG_CMD_IPROG)
        from ...protocol import base
        adapter = self.parent_of_class(base.Interface)
        adapter.reset(True)
        adapter.reset(False)
        
@Series67.application_db.register("spi")
def spi_interface(tap):
    from ...loadable.object import Program
    from ...package_resource import PackageResource

    fw_name = f"fw/{int(tap.idcode.drop_revision()):#010x}_jtag_spi.bit.gz"
    resource = PackageResource(__package__, fw_name)
    if not resource.exists():
        raise db.NoMatch("spi")
    with resource.path() as filename:
        tap.load(Program.from_file(str(filename)))

    from ..jtag_spi_bridge import JtagSpiBridge
    return JtagSpiBridge(tap, tap.USER_IR[0], tap.USER_IR[1], tap.max_freq)

