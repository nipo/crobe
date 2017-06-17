from .. import model

__all__ = ['Enumerator', 'Adapter']

registry = []

class Enumerator(model.Component):
    @classmethod
    def register(cls, enum_class):
        cls.singleton.children.append(enum_class())
        return enum_class

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

Enumerator.singleton = Enumerator("root")
