from . import model
from .ftdi import basic

__all__ = []

class Adapter(basic.Adapter):
    supported_interfaces = ["jtag", "swd", "jtag-int"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0x7c2d, gpio_value = 0x0c20,
                                       channel = "A",
                                       resetn_pin = 11,
                                       activity_pin = 15)
        elif interface_name == "jtag-int":
            return basic.Adapter.open(self, "jtag", channel = "B")
        elif interface_name == "swd":
            return basic.Adapter.open(self, interface_name,
                                      oen_pin = 12,
                                      gpio_output = 0x7c25, gpio_value = 0x0c00,
                                       channel = "A",
                                       resetn_pin = 11,
                                       activity_pin = 15)

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Busblaster",
                                       short_name = "bb",
                                       vid = 0x0403, pid = 0x8878)
