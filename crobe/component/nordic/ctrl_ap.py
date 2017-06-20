from ..arm.ap import Ap

@Ap.db.register(0x02880000)
class CtrlAp(Ap):
    RESET = 0x00
    ERASEALL = 0x04
    ERASEALLSTATUS = 0x08
    APPROTECTSTATUS = 0x0c

    def __init__(self, dp, index):
        Ap.__init__(self, dp, index)
        self.name = "Nordic Ctrl-AP"

    def erase_all(self):
        return self.reg_write(self.ERASEALL, 1)
        while self.reg_read(self.ERASEALLSTATUS):
            pass

    @property
    def protected(self):
        return not self.reg_read(self.APPROTECTSTATUS)

    @property
    def reset(self):
        return int(self.reg_read(self.RESET))

    @reset.setter
    def reset(self, value):
        return self.reg_write(self.RESET, int(bool(value)))
