from ...model import PortComponent
from ...protocol import swd, i2c, chipcon, jtag
from ...component.nsl.bnoc import sized, routed
from ...component.nsl.transactor.cs import ControlStatus

class ProbyRegs(ControlStatus):
    def __init__(self, port):
        super().__init__(port, "Regs")

    def base_freq_get(self):
        return self.reg_read(0)

    def srst_get(self):
        return self.reg_read(1) & 1

    def srst_set(self, asserted):
        return self.reg_write(1, asserted)

    def mode_get(self):
        return self.reg_read(3) & 3

    def mode_set(self, mode):
        return self.reg_write(3, mode)

class SwdInterface(swd.Interface):
    def __init__(self, meta, framed_swd, cs, base_freq):
        from ...component.nsl.transactor.swd import SwdTransactor

        self.swd = SwdTransactor(framed_swd, base_freq)
        self.cs = cs
        self.__turnaround_cycles = 1
        self.__turnaround_dirty = True
        self.__reset = False

        super().__init__(meta, "swd")

    @property
    def reset(self):
        return self.__reset

    @reset.setter
    def reset(self, value):
        if self.__reset == bool(value):
            return

        self.logger.info("%s reset pin", "holding" if value else "releasing")
        self.cs.srst_set(value)
        
    def freq_update(self, freq):
        return self.swd.freq_update(freq)
        
    @property
    def turnaround_cycles(self):
        return self.swd.turnaround_cycles

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        self.swd.turnaround_cycles = cycles

    def execute(self, op_list):
        self.swd.execute(op_list)

class JtagInterface(jtag.Interface):
    def __init__(self, meta, framed_jtag, cs, base_freq):
        from ...component.nsl.transactor.jtag import JtagTransactor
        self.jtag = JtagTransactor(framed_jtag, base_freq)
        self.cs = cs
        super().__init__(meta, "jtag")

    def execute(self, op_list):
        self.jtag.execute(op_list)

    def freq_update(self, freq):
        return self.jtag.freq_update(freq)

    @property
    def reset(self):
        return self.__reset

    @reset.setter
    def reset(self, value):
        if self.__reset == bool(value):
            return

        self.logger.info("%s reset pin", "holding" if value else "releasing")
        self.cs.srst_set(value)

class I2cInterface(i2c.Interface):
    def __init__(self, meta, framed_i2c, base_freq):
        from ...component.nsl.transactor.i2c import I2cTransactor

        self.i2c = I2cTransactor(framed_i2c, base_freq)

        super().__init__(meta, "i2c")

    def freq_update(self, freq):
        return self.i2c.freq_update(freq)

    def execute(self, op_list):
        self.i2c.execute(op_list)

class CcInterface(chipcon.Interface):
    def __init__(self, meta, framed_cc, base_freq):
        from ...component.nsl.transactor.cc import CcTransactor
        self.cc = CcTransactor(framed_cc, base_freq)
        super().__init__(meta, "cc")

    def freq_update(self, freq):
        return self.cc.freq_update(freq)

    @property
    def reset(self):
        return self.cc.reset

    @reset.setter
    def reset(self, value):
        self.cc.reset = value

class Meta(PortComponent):
    def __init__(self, port, mode):

        super().__init__(port, "jtag_swd_i2c")
        port.reprogram("jtag_swd_i2c")

        self.fifo = port.device.open(interface = "A", mode = "ft245_sync_fifo")
        self.pipe = sized.Sized(self.fifo)
        self.pipe.reset()

        self.router = routed.Router(self.pipe)
        self.cs = ProbyRegs(routed.FramedEndpoint(routed.Route(self.router, 0xf, 0x3)))

        self.base_freq = self.cs.base_freq_get()

        if mode == "swd":
            self.cs.mode_set(0)
            self.interface = SwdInterface(
                self,
                routed.FramedEndpoint(routed.Route(self.router, 0xf, 0x0)),
                self.cs,
                self.base_freq)

        elif mode == "jtag":
            self.cs.mode_set(1)
            self.interface = JtagInterface(
                self,
                routed.FramedEndpoint(routed.Route(self.router, 0xf, 0x1)),
                self.cs,
                self.base_freq)

        elif mode == "i2c":
            self.interface = I2cInterface(
                self,
                routed.FramedEndpoint(routed.Route(self.router, 0xf, 0x2)),
                self.base_freq)

        elif mode == "cc":
            self.cs.mode_set(2)
            self.interface = CcInterface(
                self,
                routed.FramedEndpoint(routed.Route(self.router, 0xf, 0x4)),
                self.base_freq)

