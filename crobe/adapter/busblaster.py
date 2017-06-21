from . import model
from .ftdi.basic import JtagAdapterEnumerator, Adapter

__all__ = []

class BBAdapter(Adapter):
    supported_interfaces = ["jtag", "swd"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return Adapter.open(self, interface_name,
                                gpio_output = 0x7c2d, gpio_value = 0x0c20)
        elif interface_name == "swd":
            return Adapter.open(self, interface_name,
                                oen_pin = 12,
                                gpio_output = 0x7c25, gpio_value = 0x0c00)

@model.Enumerator.register
class Enumerator(JtagAdapterEnumerator):
    adapter_class = BBAdapter

    def __init__(self):
        JtagAdapterEnumerator.__init__(self, "Busblaster",
                                       short_name = "bb",
                                       vid = 0x0403, pid = 0x8878,
                                       channel = "A",
                                       resetn_pin = 11,
                                       activity_pin = 15)

@model.Enumerator.register
class Enumerator(JtagAdapterEnumerator):
    def __init__(self):
        JtagAdapterEnumerator.__init__(self, "Busblaster Internal",
                                       short_name = "int-bb",
                                       vid = 0x0403, pid = 0x8878,
                                       channel = "B")
