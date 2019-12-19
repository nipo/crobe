from .. import model
from ..util.pretty import metric, sci_parse
import threading
import time

__all__ = ["Interface", "ProtocolError", "CommunicationError"]

class FreqCapper:
    def __init__(self):
        self.__freq_constraints = {}
        self.__freq = None

    def freq_cap(self, key, freq = None):
        if freq is None:
            self.__freq_constraints.pop(key, None)
        else:
            self.__freq_constraints[key] = freq
        caps = [(f, k) for (k, f) in self.__freq_constraints.items() if f]
        caps.sort(key = lambda x:x[0])
        if not caps:
            self.__freq_set()
        else:
            self.__freq_set(caps[0][0], caps[0][1])

    def __freq_set(self, freq = None, reason = ""):
        if freq == self.__freq:
            return
        self.__freq = freq
        self.freq = freq

        if not freq:
            self.logger.debug("Frequency now uncapped, had %s", metric(self.freq, "Hz"))
        else:
            self.logger.debug("Frequency now capped to %s because of %s, had %s",
                             metric(freq, "Hz"), reason, metric(self.freq, "Hz"))

    # property, writable, Hz
    freq = None

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
        self.port.child_remove(self)

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
