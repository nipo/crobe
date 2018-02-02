from . import model
from .ftdi import basic

__all__ = []

# HS2 wiring

# TCK    AD0            -Buf0>  TCK
# TDO    AD2  <Mux0/0-          TDO
#                  /1-          TMS
# TMS    AD3  -0/Mux1>  -Buf2>  TMS
# TDI    AD1  -1        -Buf1>  TDI
# TMSoe  AD5  Buf2/oe
# TDIoe  AD6  Buf1/oe
# TCKoe  AD7  Buf0/oe
# TDOsel AC5  Mux0/Sel
# TMSsel AC6  Mux1/Sel

# SMT2 wiring

# GP0    AC0            <Buf3>  GP0
# GP1    AC1            <Buf4>  GP1
# GP0oe  AC2  Buf3/out
# GP1oe  AC3  Buf4/out
# GP2oe  AC4  Buf5/out
# GP2    AC5            <Buf5>  GP2

# GP2 is meant to be a Reset.  If both HS2 and SMT2 layouts are used
# at the same time, FTDI TDO input cannot read TMS pin while in reset.

class Adapter(basic.Adapter):
    supported_interfaces = ["jtag", "swd"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0xece0, gpio_value = 0x00e0,
                                      resetn_pin = 13, reset_oe_pin = 12)
        elif interface_name == "swd":
            return basic.Adapter.open(self, interface_name,
                                      oe_pin = 5,
                                      gpio_output = 0xece0, gpio_value = 0x60a0,
                                      resetn_pin = 13, reset_oe_pin = 12)

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Digilent HS2",
                                       short_name = "hs2",
                                       vid = 0x0403, pid = 0x6014,
                                       channel = "A")
    def filter(self, adapter):
        return adapter.device.vendor == "Digilent" and adapter.device.model in ["Digilent USB Device"]

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Digilent Board",
                                       short_name = "dig",
                                       vid = 0x0403, pid = 0x6010,
                                       channel = "A")

    def filter(self, adapter):
        return adapter.device.vendor == "Digilent" and adapter.device.model in ["Digilent USB Device",
                                                                                "Digilent Adept USB Device"]
