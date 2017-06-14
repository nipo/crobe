from .model import MemoryMappedComponent

@MemoryMappedComponent.class_db.register(0x1)
class RomTable(MemoryMappedComponent):
    def __init__(self, bus, base):
        MemoryMappedComponent.__init__(self, bus, base)
        if self.component_class != 0x1:
            raise ValueError("Component is not a RomTable")

        for i in range(0, 960):
            e = self.reg_read(i * 4)

            if not e:
                break
            
            if not (e & 1):
                continue

            address_offset = e & ~0x3ff
            c = MemoryMappedComponent(self.bus, (self.base + address_offset) & 0xffffffff).cast()
            self.logger.info("- %d: %s", i, c)
            self.children.append(c)

    def __str__(self):
        return "ROM Table"
