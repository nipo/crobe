from . import model
from .ftdi import basic

__all__ = []

class Adapter(basic.Adapter):
    supported_interfaces = ["jtag", "spi"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0x0d, gpio_value = 0x0000,
                                      channel = "A")

@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Sipeed",
                                         short_name = "sp",
                                         vid = 0x0403, pid = 0x6010)

    def filter(self, adapter):
        return adapter.device.model in [
            "Sipeed-Debug",
        ]
