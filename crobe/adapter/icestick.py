from . import model
from .ftdi import basic

__all__ = []

class Adapter(basic.Adapter):
    supported_interfaces = ["spi"]
    freq_max = 30e6

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "IceStick", "ice",
                                         vid = 0x0403, pid = 0x6010, channel = "A",
                                         csn_pin = 4, resetn_pin = 7,
                                         gpio_output = 0x93, gpio_value = 0x10)

    def filter(self, adapter):
        return adapter.device.vendor == "Lattice" and adapter.device.model == "Lattice FTUSB Interface Cable"
