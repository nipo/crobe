from . import model
from .ftdi import basic
import struct

__all__ = []

class UsbBlaster3Adapter(basic.Adapter):
    supported_interfaces = ["jtag"]

    def open(self, interface_name, **kwargs):
        return basic.Adapter.open(self, "jtag",
                                  gpio_output = 0xfb, gpio_value = 0xfa,
                                  activityn_pin = 6,
                                  **kwargs)

@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = UsbBlaster3Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "ub3",
                                       short_name = "ub3",
                                       vid = 0x09fb, pid = 0x6026,
                                       channel = "A")
