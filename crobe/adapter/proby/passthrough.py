from .. import model
from ..ftdi import basic
from . import base

class Adapter(basic.Adapter, base.Reflasher):
    supported_interfaces = ["jtag", "swd", "spi"]

    def open(self, interface_name):
        self.reprogram("jtag_swd_raw")

        if interface_name == "spi":
            return basic.Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                csn_pin = 3,
                                gpio_output = 0x061b, gpio_value = 0x0210)
        elif interface_name == "jtag":
            return basic.Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                gpio_output = 0x061b, gpio_value = 0x0210)
        elif interface_name == "swd":
            return basic.Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                oe_pin = 5,
                                gpio_output = 0x063b, gpio_value = 0x0610)

@model.Enumerator.register
class Enumerator(base.Enumerator):
    adapter_class = Adapter

    def __init__(self):
        base.Enumerator.__init__(self, "Proby", "proby")
