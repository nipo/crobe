from . import model
from .ftdi import basic

__all__ = []

class Adapter(basic.Adapter):
    supported_interfaces = ["jtag", "swd", "i2c"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0xeb, gpio_value = 0x20,
                                      channel = "A",
                                      reset_od_pin = 4)
        elif interface_name == "swd":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0xe3, gpio_value = 0xc0,
                                      channel = "A",
                                      oen_pin = 6,
                                      reset_od_pin = 4)
        elif interface_name == "i2c":
            return basic.Adapter.open(self, interface_name,
                                      has_scl_in = True,
                                      gpio_output = 0, gpio_value = 0,
                                      channel = "B")

@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Hub Debug",
                                         short_name = "hd",
                                         vid = 0x0403, pid = 0x6011)

    def filter(self, adapter):
        return adapter.device.vendor == "Nipo" and adapter.device.model == "Hub Debug"
