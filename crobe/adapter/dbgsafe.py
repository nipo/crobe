from . import model
from .ftdi import basic, ftdi

__all__ = []

class Adapter(basic.Adapter):
    supported_interfaces = ["jtag", "swd", "i2c"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0x9a3b, gpio_value = 0x0a20,
                                       channel = "A",
                                       resetn_pin = 9,
                                       activity_pin = 15)
        elif interface_name == "swd":
            return basic.Adapter.open(self, interface_name,
                                      oen_pin = 12,
                                      gpio_output = 0x9a33, gpio_value = 0x0a00,
                                       channel = "A",
                                       resetn_pin = 9,
                                       activity_pin = 15)
        elif interface_name == "i2c":
            return basic.Adapter.open(self, interface_name,
                                      has_scl_in = False,
                                      gpio_output = 0x0030, gpio_value = 0x0010,
                                      channel = "A",
                                      activity_pin = 15)

@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "DbgSafe",
                                         short_name = "ds",
                                         vid = 0x0403, pid = 0x6010)

    def filter(self, adapter):
        return adapter.device.vendor == "Diaxen" and adapter.device.model == "DbgSafe 1.0"
