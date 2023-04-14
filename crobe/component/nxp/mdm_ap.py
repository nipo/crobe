import time
from ...bitfield import Bitfield, BooleanField
from ..arm.dp import DpAccessFailure
from ..arm.ap import Ap

@Ap.db.register(0x001c0020)
class MdmAp(Ap):
    STATUS = 0x00
    class Status(Bitfield):
        MassEraseAck  = BooleanField(0)
        FlashReady    = BooleanField(1)
        SystemSecurity= BooleanField(2)
        SystemReset   = BooleanField(3)
        MassEraseEn   = BooleanField(5)
        BackdoorEn    = BooleanField(6)
        LpEn          = BooleanField(7)
        VlpEn         = BooleanField(8)
        VllsExit      = BooleanField(10)
        CoreHalted    = BooleanField(16)
        CoreSleepdeep = BooleanField(17)
        CoreSleeping  = BooleanField(18)

    CONTROL           = 0x04
    class Control(Bitfield):
        MassErasing   = BooleanField(0)
        DebugDisable  = BooleanField(1)
        DebugReq      = BooleanField(2)
        ResetReq      = BooleanField(3)
        CoreHoldReset = BooleanField(4)
        VllDbgReq     = BooleanField(5)
        VllDbgAck     = BooleanField(6)
        VllsSack      = BooleanField(7)

    def __init__(self, dp, index):
        Ap.__init__(self, dp, index)
        self.name = "Kinetis MDM-AP"

    def erase_all(self):
        if not self.status.MassEraseEn:
            raise ValueError("Chip is mass-erase protected")

        self.control_mod(DebugReq = True, ResetReq = True, CoreHoldReset = True)
        self.control_mod(ResetReq = False, CoreHoldReset = False)

        self.control_mod(MassErasing = True)
        for left in range(127, -1, -1):
            try:
                if self.status.MassEraseAck:
                    break
            except DpAccessFailure as f:
                #if left == 0:
                #    raise
                pass
            time.sleep(0.01)

        for left in range(127, -1, -1):
            try:
                if not self.control.MassErasing:
                    break
            except DpAccessFailure as f:
                #if left == 0:
                #    raise
                pass
            time.sleep(0.01)
        if self.control.MassErasing:
            raise RuntimeError("Mass erase failed")
        self.logger.info("Mass erase done")

    def connect(self, value = True):
        if value:
            self.control_mod(DebugReq = True, DebugDisable = False)
        else:
            self.control_mod(DebugReq = False, DebugDisable = True)

    @property
    def protected(self):
        self.status.SystemSecurity

    @property
    def reset(self):
        self.status.SystemReset

    @reset.setter
    def reset(self, value):
        self.control_mod(ResetReq = bool(value))

    @property
    def status(self):
        ret = self.reg_read(self.STATUS)
        ret = self.Status(all = ret)
        self.logger.info("> %s", ret)
        return ret

    @status.setter
    def status(self, value):
        self.logger.info("< %s", value)
        self.reg_write(self.STATUS, int(value))

    def status_mod(self, **kwargs):
        self.logger.info("M Status %s", str(kwargs))
        s = self.status
        for k, v in kwargs.items():
            setattr(s, k, v)
        self.status = s
        
    @property
    def control(self):
        ret = self.reg_read(self.CONTROL)
        ret = self.Control(all = ret)
        self.logger.info("> %s", ret)
        return ret

    @control.setter
    def control(self, value):
        self.logger.info("< %s", value)
        self.reg_write(self.CONTROL, int(value))

    def control_mod(self, **kwargs):
        self.logger.info("M Control %s", str(kwargs))
        s = self.control
        for k, v in kwargs.items():
            setattr(s, k, v)
        self.control = s
