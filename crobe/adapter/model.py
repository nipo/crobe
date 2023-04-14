from .. import model
from collections import deque
from ..protocol import pipe
import threading
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
                #try:
                child = owner.from_device(dev)
                #except Exception as e:
                #    print(e)
                #    continue
                self.child_add(child)

        super().start()
    

class BackgroundWriter(threading.Thread):
    def __init__(self, owner, device, ep):
        self.owner = owner
        threading.Thread.__init__(self, daemon = True)
        self.device = device
        self.ep = ep

        self.queue = deque()
        self.cond = threading.Condition()
        self.running = False
        self.exception = None

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False
        with self.cond:
            self.cond.notify_all()
        super().join()
        if self.exception:
            raise self.exception
        
    def write(self, data, timeout = None):
        with self.cond:
            self.queue.append((data, timeout))
            self.cond.notify_all()

    def flush(self):
        with self.cond:
            while self.queue and self.running:
                self.cond.wait()

    def run(self):
        with self.cond:
            while self.running:
                try:
                    data, timeout = self.queue.popleft()
                except IndexError:
                    self.cond.wait()
                    continue

                try:
                    self.owner.logger.protocol("%02x < %s", self.ep.bEndpointAddress, data.hex())
                    self.device.write(self.ep.bEndpointAddress, data, int((timeout or 1.) * 1000))
                except Exception as e:
                    self.exception = e
                    return
                self.cond.notify_all()

class BulkStreamPair(pipe.Interface):
    def __init__(self, port, device, name, out_ep, in_ep):
        super().__init__(port, name = name)
        self.device = device
        self.out_ep = out_ep
        self.in_ep = in_ep
        self.__bw = BackgroundWriter(self, device, out_ep)
        self.__bw.start()

    def execute(self, blob, read_size = 0):
        self.logger.protocol("Execute, %d out, %d in", len(blob), read_size)
        self.bulk_out(blob)
        rbuf = b''
        while len(rbuf) < read_size:
            rbuf += self.bulk_in(512)
        return rbuf

    def _do_read(self, size, timeout):
        self.logger.protocol("%02x > %s", self.in_ep.bEndpointAddress, size)
        data = self.device.read(self.in_ep.bEndpointAddress,
                                self.in_ep.wMaxPacketSize,
                                int((timeout or 1.) * 1000))
        data = bytes(data)
        self.logger.protocol("-> %s", data.hex())
        return data
    
    def execute(self, operation_list, timeout = None):
        for op in operation_list:
            if isinstance(op, pipe.Write):
                self.__bw.write(op.data, timeout)

            elif isinstance(op, pipe.Read):
                op.data = self._do_read(op.size, timeout)

            elif isinstance(op, pipe.WriteRead):
                self.__bw.write(op.wdata, timeout)
                op.rdata = self._do_read(op.rsize, timeout)

            else:
                raise base.ProtocolError("Unknown Pipe operation %s" % type(op))
        self.__bw.flush()
        
    
