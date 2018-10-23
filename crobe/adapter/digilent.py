from . import model
from .ftdi import basic

__all__ = []

# HS2 wiring



# SMT2 wiring

# TCK    AD0+AD4        -Buf0>  TCK
# TDO    AD2  <Mux0/0-          TDO
#                  /1-          TMS
# TMS    AD3  -0/Mux1>  -Buf2>  TMS
# TDI    AD1  -1        -Buf1>  TDI
# TMSoen AD5  Buf2/oen
# TDIoe  AD6  Buf1/oe
# TCKoe  AD7  Buf0/oe
# TDOsel AC7  Mux0/Sel
# TMSsel AC6  Mux1/Sel
# GP0    AC0            <Buf3>  GP0
# GP1    AC1            <Buf4>  GP1
# GP0oen AC2  Buf3/out
# GP1oen AC3  Buf4/out
# GP2oen AC4  Buf5/out
# GP2    AC5            <Buf5>  GP2

# GP2 is meant to be a Reset.  If both HS2 and SMT2 layouts are used
# at the same time, FTDI TDO input cannot read TMS pin while in reset.

class DigilentAdapter(basic.Adapter):
    supported_interfaces = ["jtag", "swd"]

    def open(self, interface_name, **kwargs):
        oe = 0
        value = 0

        pins = self.mapping[interface_name + "_pins"]
        
        for pin, val in pins.items():
            if pin is None:
                continue
            oe |= 1 << pin
            if val:
                value |= 1 << pin

        if interface_name == "swd":
            pin, pol = self.mapping["swdio_oe"]

            if pol:
                kwargs["oe_pin"] = pin
            else:
                kwargs["oen_pin"] = pin

        kwargs.update(self.mapping.get("reset", {}))

        return basic.Adapter.open(self, interface_name,
                                  gpio_output = oe, gpio_value = value,
                                  **kwargs)

class Smt2Adapter(DigilentAdapter):
    tms_oen = 5
    tdi_oe = 6
    tck_oe = 7
    tdo_sel = 15 # FTDI TDO   from  0: target TDO, 1: target TMS
    tms_sel = 14 # Target TMS from  0: FTDI TMS, 1: FTDI TDI
    gp0 = 8
    gp1 = 9
    gp2 = 13 # Supposed to be RESET
    gp0_dir_in = 10
    gp1_dir_in = 11
    gp2_dir_in = 12

    mapping = dict(
        jtag_pins = {
            tdi_oe: 1,
            tck_oe: 1,
            tms_oen: 0,
            tdo_sel: 0,
            tms_sel: 0,
        },
        swd_pins = {
            tdi_oe: 0,
            tck_oe: 1,
            tdo_sel: 1,
            tms_sel: 1,
        },
        swdio_oe = (tms_oen, 0),
        reset = dict(
            resetn_pin = gp2,
            reset_oen_pin = gp2_dir_in,
        ),
        )

class Hs2Adapter(DigilentAdapter):
    tms_oe = 5
    tdi_oe = 6
    tck_oe = 7

    mapping = dict(
        jtag_pins = {
        tms_oe: 1,
        tdi_oe: 1,
        tck_oe: 1,
        13: 0,
        14: 0,
        },
        swd_pins = {
        tms_oe: 0,
        tdi_oe: 0,
        tck_oe: 1,
        13: 1,
        14: 1,
        },
        swdio_oe = (tms_oe, 1),
        )

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Hs2Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Digilent HS2",
                                       short_name = "hs2",
                                       vid = 0x0403, pid = 0x6014,
                                       channel = "A")
    def filter(self, adapter):
        return adapter.device.vendor == "Digilent" and adapter.device.model in ["Digilent USB Device"]

@model.Enumerator.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = Smt2Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Digilent Board",
                                       short_name = "dig",
                                       vid = 0x0403, pid = 0x6010,
                                       channel = "A")

    def filter(self, adapter):
        return adapter.device.vendor == "Digilent" and adapter.device.model in ["Digilent USB Device",
                                                                                "Digilent Adept USB Device"]
