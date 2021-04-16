from .. import model
from ..util.pretty import metric, sci_parse
from ..freq_capper import FreqCapper
import threading
import time

__all__ = ["Interface", "ProtocolError", "CommunicationError"]

class Interface(model.PortComponent, FreqCapper):
    """
    Base class for protocol interfaces from an Adapter.
    """
    power = None

    def __init__(self, port, name):
        self.do_reset = False
        model.PortComponent.__init__(self, port, name)
        FreqCapper.__init__(self)
        self._lock = threading.Lock()
        self.__reset = None
        self.__wait = 0
        self.__do_power = None
        
    def close(self):
        #self.port.child_remove(self)
        pass

    def option_set(self, opt):
        if opt == "reset":
            self.__reset = True
            return

        if opt.startswith("reset="):
            if opt[6:] == "hold":
                self.__reset = "hold"
                return
            self.__reset = float(sci_parse(opt[6:]))
            return

        if opt.startswith("wait="):
            self.__wait = float(sci_parse(opt[5:]))
            return

        if opt.startswith("fmax="):
            self.freq_cap("user", sci_parse(opt[5:]))
            return

        if opt.startswith("power="):
            opt = opt[6:].lower()
            self.__do_power = opt in ["1", "on", "true"]
            return

        super().option_set(opt)

    def start(self):
        if self.__do_power is not None:
            self.power = self.__do_power

        if self.__reset == "hold":
            self.logger.info("Holding reset")
            self.reset(True)
        elif isinstance(self.__reset, float):
            self.logger.info("Holding reset for %d sec", self.__reset)
            self.reset(True)
            time.sleep(self.__reset)
            self.reset(False)
        elif self.__reset is True:
            self.logger.info("Cycling reset", self.__reset)
            self.execute([self.cmd_reset(True), self.cmd_reset(False)])

        if self.__wait:
            self.logger.info("Waiting for %d sec", self.__wait)
            time.sleep(self.__wait)

        super().start()
        
    def reset(self, asserted):
        return self.execute([self.cmd_reset(asserted)])

    def cmd_reset(self, asserted):
        return Reset(asserted)

    def _execute(self, commands):
        pass

    def execute(self, commands):
        with self._lock:
            self._execute(commands)

class Operation:
    def __repr__(self):
        return str(self)

class Reset(Operation):
    def __init__(self, asserted):
        self.asserted = asserted

    def __str__(self):
        return f"<Reset {self.asserted}>"

class ProtocolError(Exception):
    """
    Protocol violation from API usage, like when someone asks for JTAG
    data shifting while FSM is in reset, for instance
    """
    pass

class CommunicationError(Exception):

    """
    An error that happens between adapter driver and hardware.
    """
    pass
