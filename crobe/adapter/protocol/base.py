from ... import model
from ...util.pretty import sci
import threading

__all__ = ["Interface", "ProtocolError", "CommunicationError"]

class Interface(model.PortComponent):
    """
    Base class for protocol interfaces from an Adapter.
    """
    def __init__(self, port, name):
        model.PortComponent.__init__(self, port, name)
        self._lock = threading.Lock()
        self.__freq_constraints = {}
        self.__freq = None

    def close(self):
        pass

    def _execute(self, commands):
        pass

    def execute(self, commands):
        with self._lock:
            self._execute(commands)

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
            self.logger.info("Frequency now uncapped, had %s", sci(self.freq, "Hz"))
        else:
            self.logger.info("Frequency now capped to %s because of %s, had %s",
                             sci(freq, "Hz"), reason, sci(self.freq, "Hz"))

    # property, writable, Hz
    freq = None

    # property read-write
    # Active high
    reset = False

    def __str__(self):
        return "%s on %s" % (self.__class__.__name__, self.port)

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
