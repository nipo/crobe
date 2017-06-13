from .. import model

__all__ = ['Enumerator', 'Adapter', 'Interface', 'JtagInterface', 'SwdInterface']

class Enumerator(model.Component):
    def __init__(self):
        model.Component.__init__(self, "Enumerator")

    def find(self, **filter):
        raise KeyError("Adapter not found")

    def get(self, **filter):
        candidates = self.find(**filter)
        if len(candidates) != 1:
            raise KeyError("Criteria not met")
        return candidates[0]

class Adapter(model.Component):
    def __init__(self, name):
        model.Component.__init__(self, name)
        
    # properties, read only:
    supported_interfaces = []
    firmware_info = ""
    serial_number = ""

    # property read-write
    # Active high
    reset = False

    def open(self, interface_name):
        raise NotSupportedError("Unsupported interface %s" % interface_name)

class Interface(model.PortComponent):
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
    pass
