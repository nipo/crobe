from . import model
from .ftdi import basic

__all__ = []

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Digilent HS2", "hs2",
                                       vid = 0x0403, pid = 0x6014, channel = "A",
                                       gpio_output = 0xe0, gpio_value = 0xe0)

    def filter(self, adapter):
        return adapter.device.vendor == "Digilent" and adapter.device.model == "Digilent USB Device"

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Digilent board", "dig",
                                       vid = 0x0403, pid = 0x6010, channel = "A",
                                       gpio_output = 0x80, gpio_value = 0x80)

    def filter(self, adapter):
        return adapter.device.vendor == "Digilent" and adapter.device.model == "Digilent USB Device"
