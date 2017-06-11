
__all__ = ['Enumerator', 'Adapter', 'Interface', 'JtagInterface', 'SwdInterface']

class Enumerator(object):
    def __init__(self):
        pass

    def find(self, **filter):
        raise KeyError("Adapter not found")

    def get(self, **filter):
        candidates = self.find(**filter)
        if len(candidates) != 1:
            raise KeyError("Criteria not met")
        return candidates[0]

class Adapter(object):
    def __init__(self):
        pass

    # properties, read only:
    supported_interfaces = []
    firmware_info = ""
    serial_number = ""

    # property read-write
    # Active high
    reset = False

    def open(self, interface_name):
        raise NotSupportedError("Unsupported interface %s" % interface_name)

class Interface(object):
    def __init__(self):
        pass

    def close(self):
        pass

    # property, writable, Hz
    speed = None

    # property, read-only
    adapter = None

    # property read-write
    # Active high
    reset = False

class ProtocolError(Exception):
    pass
