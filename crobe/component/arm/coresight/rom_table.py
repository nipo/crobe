from .... import model
from .model import MemoryMappedComponent

class FailedComponent(model.Bus32Component):
    def __init__(self, bus, base):
        super().__init__(bus, base & ~0x3ff, "<0x%08x: Failed component>" % base)

@MemoryMappedComponent.class_db.register(0x1)
class RomTable(MemoryMappedComponent):
    def __init__(self, bus, base, name = "RomTable"):
        MemoryMappedComponent.__init__(self, bus, base, name)
        if self.component_class != 0x1:
            raise ValueError("Component is not a RomTable")

    def __str__(self):
        return "RomTable for %s" % self.partid.pretty()

    def start(self):
        for addr in range(0, 0xf00, 4):
            e = self.reg_read(addr)

            if not e:
                break
            
            if not (e & 1):
                continue

            address_offset = e & ~0x3ff
            try:
                c = MemoryMappedComponent(self.bus, (self.base + address_offset) & 0xffffffff).cast()
            except:
                c = FailedComponent(self.bus, (self.base + address_offset) & 0xffffffff)
            self.logger.debug("Entry at %03x: %s", addr, c)
            self.child_add(c)

        MemoryMappedComponent.start(self)
