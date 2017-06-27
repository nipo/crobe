from ... import model
import threading

__all__ = ["Interface", "ProtocolError", "CommunicationError"]

class Interface(model.PortComponent):
    """
    Base class for protocol interfaces from an Adapter.
    """
    def __init__(self, name, port):
        model.PortComponent.__init__(self, name, port)
        self._lock = threading.Lock()

    def close(self):
        pass

    def _execute(self, commands):
        pass

    def execute(self, commands):
        with self._lock:
            self._execute(commands)
    
    # property, writable, Hz
    speed = None

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
