from .. import model

__all__ = ['Enumerator', 'Adapter']

registry = []

__doc__ = """
Adapters are devices that permit access to some given protocol
interface. They are often called 'Emulators' or 'Probes'.

Adapters can support many different protocols.

Adapters can be discovered dynamically by Enumerators. Global
enumerators are automatically registered at module import time through
the `Enumerator.signeton.register` decorator.
"""

class Enumerator(model.Component):
    """
    Adapter enumerator class. An instance of this class is created on
    registration.
    """
    
    @classmethod
    def register(cls, enum_class):
        """
        Registers an enumerator class, can be used as a decorator for
        global enumerators declaration.

        :param enum_class: Enumerator class to register
        """
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
    """
    An adapter, this is an actual 'Probe' or 'Emulator' before it is
    actually opened for a given interface protocol.

    It can be queried for supported interface protocols.
    """
    def __init__(self, name):
        model.Component.__init__(self, name)
        
    """
    Read-only property listing supported interfaces names for this Adapter.
    """
    supported_interfaces = []
    """
    Read-only property giving version information.
    """
    firmware_info = ""
    """
    Read-only property with serial number of device.
    """
    serial_number = ""

    """
    Read-write property controlling target reset. This is active
    high. If actual reset line is #resetn (active low), setting this
    property to True drives the line low.
    """
    reset = False

    def open(self, interface_name):
        """
        Opens the adapter for a given Interface protocol. Queried
        interface name should be listed in `supported_interfaces`.
        """
        raise NotSupportedError("Unsupported interface %s" % interface_name)

Enumerator.singleton = Enumerator("root")
