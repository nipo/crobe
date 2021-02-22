from . import model
from .ftdi import basic

__all__ = []

class DbgV1(basic.Adapter):
    supported_interfaces = ["jtag", "swd", "spi", "i2c", "spi_rst"]

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
        elif interface_name == "spi":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0xeb, gpio_value = 0x20,
                                      channel = "A",
                                      csn_pin = 3,
                                      reset_od_pin = 4)
        elif interface_name == "spi_rst":
            return basic.Adapter.open(self, "spi",
                                      gpio_output = 0xfb, gpio_value = 0x20,
                                      channel = "A",
                                      csn_pin = 3)
        elif interface_name == "i2c":
            return basic.Adapter.open(self, interface_name,
                                      has_scl_in = True,
                                      gpio_output = 0, gpio_value = 0,
                                      channel = "B")

@model.HwRoot.register
class EnumeratorV1(basic.AdapterEnumerator):
    adapter_class = DbgV1

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Hub Debug",
                                         short_name = "hd",
                                         vid = 0x0403, pid = 0x6011)

    def filter(self, adapter):
        return adapter.device.vendor == "Nipo" and adapter.device.model == "Hub Debug"

class DbgV2(basic.Adapter):
    supported_interfaces = ["jtag", "swd", "i2c"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0x6b, gpio_value = 0x00,
                                      channel = "A",
                                      reset_od_pin = 4)
        elif interface_name == "swd":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0x63, gpio_value = 0x20,
                                      channel = "A",
                                      oen_pin = 6,
                                      reset_od_pin = 4)
        elif interface_name == "i2c":
            return basic.Adapter.open(self, interface_name,
                                      has_scl_in = True,
                                      gpio_output = 0, gpio_value = 0,
                                      channel = "B")

@model.HwRoot.register
class EnumeratorV2(basic.AdapterEnumerator):
    adapter_class = DbgV2

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Hub Debug v2",
                                         short_name = "hd2",
                                         vid = 0x0403, pid = 0x6011)

    def filter(self, adapter):
        return adapter.device.vendor == "Nipo" and adapter.device.model == "Hub Debug v2"

class HubJtagAdapter(basic.Adapter):
    supported_interfaces = ["jtag"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0x0b, gpio_value = 0x0,
                                      channel = "A")

@model.HwRoot.register
class HubJtagEnumerator(basic.AdapterEnumerator):
    adapter_class = HubJtagAdapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "HubDbg JTAG Adapter",
                                         short_name = "hdj",
                                         vid = 0x0403, pid = 0x6014)

    def filter(self, adapter):
        return adapter.device.vendor == "Nipo" and adapter.device.model == "Hub Debug Jtag"
