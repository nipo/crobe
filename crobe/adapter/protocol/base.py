from ... import model

__all__ = ["Interface", "ProtocolError", "CommunicationError"]

class Interface(model.PortComponent):
    """
    Base class for a given protocol interface from an adapter.
    """
    def __init__(self, name, port):
        model.PortComponent.__init__(self, name, port)

    def close(self):
        pass

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
