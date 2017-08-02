from ... import model
from ...util.pretty import sci
import threading

__all__ = ["Interface", "ProtocolError", "CommunicationError"]

class Interface(model.PortComponent):
    """
    Base class for protocol interfaces from an Adapter.
    """
    def __init__(self, name, port):
        model.PortComponent.__init__(self, name, port)
        self._lock = threading.Lock()
        self.__freq_constraints = {}

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
            self.logger.info("Frequency now uncapped")
            self.freq = None
        else:
            self.logger.info("Frequency now capped to %s because of %s", sci(caps[0][0], "Hz"), caps[0][1])
            self.freq = caps[0][0]

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
