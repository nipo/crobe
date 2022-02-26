from .model import CoresightComponent

@CoresightComponent.db.register(0x11)
class Tpiu(CoresightComponent):
    def __init__(self, ap, base):
        CoresightComponent.__init__(self, ap, base, "TPIU")
        
        self.device_id = self.reg_read(self.DEVICE_ID)
        self.nrz_supported = bool(self.device_id & self.DEVICE_ID_NRZ_SUP)
        self.manchester_supported = bool(self.device_id & self.DEVICE_ID_MANCHESTER_SUP)
        self.tracedata_supported = not(self.device_id & self.DEVICE_ID_TRACEDATA_UNSUP)
        self.fifo_size = self.DEVICE_ID_FIFOSIZE(self.device_id)
        self.atclk_async = bool(self.device_id & self.DEVICE_ID_ATCLK_ASYNC)
        self.mux_level = self.DEVICE_ID_ATB_MUX(self.device_id)

        sspsr = self.reg_read(self.SSPSR)
        self.supported_widths = [x+1 for x in range(32) if sspsr & (1 << x)]

        formats = []
        if self.nrz_supported: formats.append("NRZ")
        if self.manchester_supported: formats.append("Manchester")
        if self.tracedata_supported: formats.append("Parallel")
        self.logger.note("Supports trace formats: %s", ', '.join(formats))
        self.logger.note("FIFO size: %d entries", self.fifo_size)
        self.logger.note("ATCLK is %s", "asynchronous" if self.atclk_async else "synchronous")
        self.logger.note("MUX level: %d", self.mux_level)
        self.logger.note("Supported parallel widths: %s",
                         ",".join(map(str, self.supported_widths)))

        self.formatted = False

    def stop(self):
        self.reg_write(self.FFCR, self.FFCR_STOP_FL | self.FFCR_F_ON_MAN)
        while self.reg_read(self.FFCR) & self.FFCR_F_ON_MAN:
            pass
        while self.reg_read(self.FFSR) & (self.FFSR_FT_NON_STOP | self.FFSR_FT_STOPPED) \
                  == 0:
            pass

    def output_mode_set(self, width, scaler, formatted):
        """
        :param int width: Trace port width. If 0 or None, SWO mode in NRZ is used.
        :param int scaler: Divisor for coreclk to trace clock
        :param bool formatted: Enable formatter
        """
        cmd = []
        cmd.append(self.cmd_reg_write(self.FFCR, self.FFCR_STOP_FL | self.FFCR_F_ON_MAN))
        if width:
            assert self.tracedata_supported
            cmd.append(self.cmd_reg_write(self.CPSR, 1<<(width - 1)))
            cmd.append(self.cmd_reg_write(self.CODR, 0))
            cmd.append(self.cmd_reg_write(self.SPPR, self.SPPR_PARALLEL))
        else:
            assert self.nrz_supported
            cmd.append(self.cmd_reg_write(self.CPSR, 0))
            cmd.append(self.cmd_reg_write(self.CODR, int(scaler - 1)))
            cmd.append(self.cmd_reg_write(self.SPPR, self.SPPR_NRZ))
        cmd.append(self.cmd_reg_write(self.FFCR, self.FFCR_TRIG_IN | self.FFCR_EN_F_CONT))

        self.bus.execute(cmd)

        if formatted:
            self.reg_write(self.FFCR, self.FFCR_TRIG_IN | self.FFCR_EN_F_CONT)

        while self.reg_read(self.FFSR) & (self.FFSR_FT_NON_STOP | self.FFSR_FT_STOPPED) \
                  == self.FFSR_FT_STOPPED:
            pass

        self.logger.note("CPSR: 0x%08x", self.reg_read(self.CPSR))
        self.logger.note("CODR: 0x%08x", self.reg_read(self.CODR))
        self.logger.note("SPPR: 0x%08x", self.reg_read(self.SPPR))
        self.logger.note("FFCR: 0x%08x", self.reg_read(self.FFCR))
        self.logger.note("FFSR: 0x%08x", self.reg_read(self.FFSR))

    def __str__(self):
        return "Trace Port Interface Unit"

    SSPSR       = 0x000
    CPSR        = 0x004
    CODR        = 0x010
    SPPR        = 0x0f0
    SPPR_PARALLEL   = 0
    SPPR_MANCHESTER = 1
    SPPR_NRZ        = 2
    STM         = 0x100
    TCR         = 0x104
    TMR         = 0x108
    STPMR       = 0x200
    CTPMR       = 0x204
    TPRCR       = 0x208
    FFSR        = 0x300
    FFSR_TC_PRESENT = 0x4
    FFSR_FT_STOPPED = 0x2
    FFSR_FL_IN_PROG = 0x1
    FFSR_FT_NON_STOP = 0x8
    FFCR        = 0x304
    FFCR_EN_F_TC    = 0x0001
    FFCR_EN_F_CONT  = 0x0002
    FFCR_F_ON_FL_IN = 0x0010
    FFCR_F_ON_TRIG  = 0x0020
    FFCR_F_ON_MAN   = 0x0040
    FFCR_TRIG_IN    = 0x0100
    FFCR_TRIG_EVT   = 0x0200
    FFCR_TRIG_FL    = 0x0400
    FFCR_STOP_FL    = 0x1000
    FFCR_STOP_TRIG  = 0x4000
    FSCR        = 0x308
    EXCTLI      = 0x400
    EXCTLO      = 0x404
    ITTRFLINACK = 0xee4
    ITTRFLIN    = 0xee8
    ITATBDATA0  = 0xeec
    ITATBCTR2   = 0xef0
    ITATBCTR1   = 0xef4
    ITATBCTR0   = 0xef8

    DEVICE_ID = 0xfc8
    DEVICE_ID_NRZ_SUP = 1 << 11
    DEVICE_ID_MANCHESTER_SUP = 1 << 10
    DEVICE_ID_TRACEDATA_UNSUP = 1 << 9
    DEVICE_ID_FIFOSIZE = staticmethod(lambda x: 2 ** ((x >> 6) & 7))
    DEVICE_ID_ATCLK_ASYNC = 1 << 5
    DEVICE_ID_ATB_MUX = staticmethod(lambda x: x & 0x1f)
    
