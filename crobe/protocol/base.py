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
    def __init__(self, port, name):
        self.do_reset = False
        model.PortComponent.__init__(self, port, name)
        FreqCapper.__init__(self)
        self._lock = threading.Lock()

    def close(self):
        #self.port.child_remove(self)
        pass

    def option_set(self, opt):
        if opt == "reset":
            self.do_reset = True
            return

        if opt.startswith("reset="):
            self.reset = True
            w = float(sci_parse(opt[6:]))
            time.sleep(w)
            self.reset = False
            return

        if opt.startswith("wait="):
            w = float(sci_parse(opt[5:]))
            self.logger.debug("Waiting %fs", w)
            time.sleep(float(w))
            return

        if opt.startswith("fmax="):
            self.freq_cap("user", sci_parse(opt[5:]))
            return

        if opt.startswith("power="):
            opt = opt[6:].lower()
            self.power = opt in ["1", "on", "true"]
            return

        model.PortComponent.option_set(self, opt)
            
    def _execute(self, commands):
        pass

    def execute(self, commands):
        with self._lock:
            self._execute(commands)

    # property read-write
    # Active high
    reset = False

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
