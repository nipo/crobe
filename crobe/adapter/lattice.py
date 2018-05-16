from . import model
from .ftdi import basic

__all__ = []

# HW-USBN-2B features a FT2232H, a Mach-XO2, eeproms.
# It looks like there are advanced features implemented in the Mach-XO, but undocumented.
# Lattice was kind enough to actually let the FPGA in passthrough for JTAG by default.

class Adapter(basic.Adapter):
    supported_interfaces = ["jtag", "jtag-int"]

    def open(self, interface_name):
        if interface_name == "jtag-int":
            return basic.Adapter.open(self, "jtag", channel = "B")

        elif interface_name == "jtag":
            return basic.Adapter.open(self, "jtag", channel = "A")

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Lattice HW-USBN-2B",
                                       short_name = "lat",
                                       vid = 0x0403, pid = 0x6010,
                                       channel = "A")

    def filter(self, adapter):
        return adapter.device.vendor == "Lattice" and adapter.device.model.startswith("Lattice HW-USBN-2B")
