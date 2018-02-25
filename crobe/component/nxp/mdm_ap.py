from ..arm.dp import DpAccessFailure
from ..arm.ap import Ap

@Ap.db.register(0x001c0020)
class MdmAp(Ap):
    STATUS = 0x00
    STATUS_MASS_ERASE_ACK  = (1 << 0)
    STATUS_FLASH_READY     = (1 << 1)
    STATUS_SYSTEM_SECURITY = (1 << 2)
    STATUS_SYSTEM_RESET    = (1 << 3)
    STATUS_MASS_ERASE_EN   = (1 << 5)
    STATUS_BACKDOOR_EN     = (1 << 6)
    STATUS_LP_EN           = (1 << 7)
    STATUS_VLP_EN          = (1 << 8)
    STATUS_VLLS_EXIT       = (1 << 10)
    STATUS_CORE_HALTED     = (1 << 16)
    STATUS_CORE_SLEEPDEEP  = (1 << 17)
    STATUS_CORE_SLEEPING   = (1 << 18)
    CONTROL = 0x04
    CONTROL_MASS_ERASING    = (1 << 0)
    CONTROL_DEBUG_DISABLE   = (1 << 1)
    CONTROL_DEBUG_REQ       = (1 << 2)
    CONTROL_RESET_REQ       = (1 << 3)
    CONTROL_CORE_HOLD_RESET = (1 << 4)
    CONTROL_VLLDBGREQ       = (1 << 5)
    CONTROL_VLLDBGACK       = (1 << 6)
    CONTROL_VLLS_SACK       = (1 << 7)

    def __init__(self, dp, index):
        Ap.__init__(self, dp, index)
        self.name = "Kinetis MDM-AP"

    def erase_all(self):
        if not (self.status & self.STATUS_MASS_ERASE_EN):
            raise ValueError("Chip is mass-erase protected")

        self.control = self.CONTROL_MASS_ERASING
        for count in range(128):
            try:
                if self.status & self.STATUS_MASS_ERASE_ACK:
                    break
            except DpAccessFailure as f:
                pass

    def connect(self, value = True):
        self.control = self.CONTROL_DEBUG_REQ if value else self.CONTROL_DEBUG_DISABLE

    @property
    def protected(self):
        return bool(self.status & self.STATUS_SYSTEM_SECURITY)

    @property
    def reset(self):
        return bool(self.control & self.STATUS_SYSTEM_RESET)

    @reset.setter
    def reset(self, value):
        self.control = self.STATUS_SYSTEM_RESET if value else 0

    @property
    def status(self):
        return self.reg_read(self.STATUS)

    @status.setter
    def status(self, value):
        self.reg_write(self.STATUS, value)

    @property
    def control(self):
        return self.reg_read(self.CONTROL)

    @control.setter
    def control(self, value):
        self.reg_write(self.CONTROL, value)
