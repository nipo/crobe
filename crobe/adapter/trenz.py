from . import model
from .ftdi import basic
import struct

__all__ = []

class Tei0003Adapter(basic.Adapter):
    supported_interfaces = ["jtag"]

    def open(self, interface_name, **kwargs):
        return basic.Adapter.open(self, "jtag",
                                  gpio_output = 0x0b, gpio_value = 0x00,
                                  **kwargs)

@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Tei0003Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "tei",
                                       short_name = "tei",
                                       vid = 0x0403, pid = 0x6010,
                                       channel = "A")
    def filter(self, adapter):
        return adapter.device.vendor == "Arrow" and adapter.device.model.startswith("Arrow USB Blaster")
