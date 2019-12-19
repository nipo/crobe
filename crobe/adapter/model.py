from .. import model
from .. import db

__all__ = ['Adapter', 'HwRoot', 'SelfEnumerator', 'ExplicitEnumerator', 'UsbEnumerator']

__doc__ = """
Adapters are devices that permit access to some given protocol
interface. They are often called 'Emulators' or 'Probes'.

Adapters can support many different protocols.

Adapters can be discovered dynamically by Enumerators.
"""

class _HwRoot(model.Component):
    """
    Adapter/Enumerator registry.
    """

    def register(self, enumerator_klass):
        self.child_add(enumerator_klass())
        return enumerator_klass
    
HwRoot = _HwRoot("HwRoot")
                 
class Enumerator(model.Component):
    pass

class AutoEnumerator(Enumerator):
    pass

class ExplicitEnumerator(Enumerator):
    pass

class Adapter(model.Component):
    """
    An adapter, this is an actual 'Probe' or 'Emulator' before it is
    actually opened for a given interface protocol.

    It can be queried for supported interface protocols.
    """
        
    """
    Read-only property listing supported interfaces names for this Adapter.
    """
    supported_interfaces = []

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
        return None

    def child_spawn(self, name):
        return self.open(name)

class UsbInfo:
    def __init__(self, **kwargs):
        self.__crit = kwargs

    def is_matching(self, device):
        return all((getattr(device, k) == v) for (k, v) in self.__crit.items())

    def __hash__(self):
        h = 0
        for k, v in sorted(self.__crit.items()):
            h ^= hash(k)
            h ^= hash(v)
            h >>= 1
        return h

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        if len(self.__crit) != len(other.__crit):
            return False
        for (k1, v1), (k2, v2) in zip(sorted(self.__crit.items()),
                                      sorted(other.__crit.items())):
            if k1 != k2 or v1 != v2:
                return False
        return True
        
@HwRoot.register
class UsbEnumerator(AutoEnumerator):
    """USB Auto enumerator"""

    def __init__(self):
        model.Component.__init__(self, "USB")
    
    db = db.Db("USB device", eq_func = UsbInfo.is_matching)

    def start(self):
        import usb.core
        for dev in usb.core.find(find_all = True):
            try:
                owners = self.db.get(dev, allow_default = False)
                self.logger.debug("Device %03d/%03d %04x:%04x, %d drivers", dev.bus, dev.address, dev.idVendor, dev.idProduct, len(owners))
            except db.NoMatch:
                self.logger.debug("Device %03d/%03d %04x:%04x, 0 drivers", dev.bus, dev.address, dev.idVendor, dev.idProduct)
                continue
            for owner in owners:
                self.logger.debug(" - using %s", owner)
                try:
                    child = owner.from_device(dev)
                except Exception as e:
                    print(e)
                    continue
                self.child_add(child)

        super().start()
