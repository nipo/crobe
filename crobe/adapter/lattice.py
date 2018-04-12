from . import model
from .ftdi import basic

__all__ = []

# HW-USBN-2B features a FT2232H, a Mach-XO2, eeproms.
# It looks like there are advanced features implemented in the Mach-XO, but undocumented.
# Lattice was kind enough to actually let the FPGA in passthrough for JTAG by default.

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Lattice HW-USBN-2B",
                                       short_name = "lat",
                                       vid = 0x0403, pid = 0x6010,
                                       channel = "A")

    def filter(self, adapter):
        return adapter.device.vendor == "Lattice" and adapter.device.model.startswith("Lattice HW-USBN-2B")

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Lattice HW-USBN-2B Internal Chain",
                                       short_name = "int-lat",
                                       vid = 0x0403, pid = 0x6010,
                                       channel = "B")

    def filter(self, adapter):
        return adapter.device.vendor == "Lattice" and adapter.device.model.startswith("Lattice HW-USBN-2B")
