from ..arm.ap import Ap

@Ap.db.register(0x16e60001)
class AuthenticationAp(Ap):
    CMD               = 0x00
    CMD_DEVICE_ERASE  = 1
    CMD_DEVICE_RESET  = 2

    CMDKEY            = 0x04
    CMDKEY_MAGIC      = 0xcfacc118

    STATUS            = 0x08
    STATUS_ERASE_BUSY = 1

    def __init__(self, dp, index):
        Ap.__init__(self, dp, index)
        self.name = "Energy Micro Authentication-AP"

    def erase_all(self):
        self.reg_write(self.CMDKEY, self.CMDKEY_MAGIC)
        self.reg_write(self.CMD, self.CMD_DEVICE_ERASE)
        while self.reg_read(self.STATUS) & self.STATUS_ERASE_BUSY:
            pass
        self.reg_write(self.CMD, self.CMD_DEVICE_RESET)

    @property
    def protected(self):
        return True

    def reset(self):
        self.reg_write(self.CMD, self.CMD_DEVICE_RESET)
