from . import model
from .ftdi import basic
import struct

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

class Serial:
    VERSION = 1
    MAGIC = 0x0056
    END = 0x0048

    FORMAT = "<HHLL17s29sHH46sH"
    HEADER_BLOB = struct.pack("<HH", MAGIC, VERSION)
    SIZE = struct.calcsize(FORMAT)

    def __init__(self, oemid, pdid,
                 user_name, product_name,
                 dcap_pub, dcap_priv):
        self.oemid = oemid
        self.pdid = pdid
        self.product_name = product_name
        self.user_name = user_name
        self.dcap_pub = dcap_pub
        self.dcap_priv = dcap_priv

    def __bytes__(self):
        return struct.pack(self.FORMAT,
                           self.MAGIC, self.VERSION,
                           self.oemid, self.pdid,
                           self.user_name.encode("utf-8"),
                           self.product_name.encode("utf-8"),
                           self.dcap_pub, self.dcap_priv,
                           b'', self.END)

    @classmethod
    def from_bytes(cls, data):
        index = data.index(cls.HEADER_BLOB)
        (magic, version, oemid, pdid,
         user_name, product_name, dcap_pub, dcap_priv,
         pad, end) = struct.unpack(cls.FORMAT, data[index : index + cls.SIZE])
        user_name = str(user_name.rstrip(b'\0'), "utf-8", "ignore")
        product_name = str(product_name.rstrip(b'\0'), "utf-8", "ignore")
        if magic != cls.MAGIC or version != cls.VERSION or end != cls.END:
            raise ValueError("Bad framing")
        if pad.rstrip(b'\0'):
            print("Unknown data in padding")
        return cls(oemid, pdid,
                   user_name, product_name,
                   dcap_pub, dcap_priv)

    def dump(self):
        print("OEM ID: %08x" % self.oemid)
        print("PDID: %08x" % self.pdid)
        print("User name: %s" % self.user_name)
        print("Product name: %s" % self.product_name)
        print("DCap: %04x / %04x" % (self.dcap_pub, self.dcap_priv))

class FtdiSerial:
    def __init__(self,
                 manufacturer, product,
                 serial, has_b, power,
                 info):
        self.manufacturer = manufacturer
        self.product = product
        self.serial = serial
        self.has_b = has_b
        self.power = power
        self.info = info

    def dump(self):
        print("Manufacturer: %s" % self.manufacturer)
        print("Product: %s" % self.product)
        print("Serial: %s" % self.serial)
        print("Has B: %s" % bool(self.has_b))
        print("USB power: %s" % self.power)
        self.info.dump()

d = "Digilent"
dd = "Digilent USB Device"
da = "Digilent Adept USB Device"
for pd, un, pn, dpu, dpr, man, desc, has_b, power in [
        [0x30700050, "JtagHs", "JTAG-HS", 0x13, 0, "", "D", False, 500],
        [0x30700050, "JtagHs", "JTAG-HS", 0x13, 0, d, da, False, 500],
        [0x30700150, "JtagHs1", "Digilent JTAG-HS1", 0x11, 0, d, dd, False, 500],
        [0x30900152, "JtagHs2", "Digilent JTAG-HS2", 0x11, 0, d, dd, False, 500],
        [0x31100153, "JtagHs3", "Digilent JTAG-HS3", 0x1, 0, d, dd, False, 500],
        [0x30800151, "JtagSmt1", "Digilent JTAG-SMT1", 0x1, 0, d, da, False, 0],
        [0x31000154, "JtagSmt2", "Digilent JTAG-SMT2", 0x13, 0, d, dd, False, 0],
        [0x40200360, "Discovery", "Analog Discovery", 0, 0x801, d, dd, False, 500],
        [0x40300360, "Discovery2", "Analog Discovery 2", 0, 0x801, d, dd, False, 0],
        [0x40380360, "Discovery2NI", "Analog Discovery 2 NI Edition", 0, 0x801, d, dd, False, 0],
        [0x40400160, "DDiscovery", "Digital Discovery 2", 0, 0x801, d, dd, False, 0],
        [0x00e00153, "JtagOnb1", "Digilent JTAG-ONB1", 1, 0, d, dd, False, 500],
        [0x50600155, "JtagOnb2", "Digilent JTAG-ONB2", 0x811, 0, d, da, False, 500],
        [0x50700156, "JtagOnb3", "Digilent JTAG-ONB3", 0x811, 0, d, da, False, 500],
        [0x50800157, "JtagOnb4", "Digilent JTAG-ONB4", 0x1, 0, d, da, True, 500],
        [0x00e00153, "Zed", "Digilent ZED", 0x1, 0, d, dd, False, 500],
        [0x01000151, "Anvyl", "Digilent Anvyl", 0x1, 0, d, da, True, 500],
        [0x01200151, "Nexys4", "Digilent Nexys 4", 0x1, 0, d, da, True, 500],
        [0x01700151, "Nexys4", "Digilent Nexys 4 DDR", 0x1, 0, d, da, True, 500],
        [0x01500157, "Zybo", "Digilent Zybo", 0x1, 0, d, da, True, 500],
        [0x01600155, "NexysVideo", "Digilent Nexys Video", 0x811, 0, d, da, False, 0],
        [0x01800151, "Basys3", "Digilent Basys 3", 0x1, 0, d, da, True, 500],
        [0x01300155, "Genesys2", "Digilent Genesys 2", 0x811, 0, d, da, False, 0],
        [0x01900151, "NetFPGA10", "Digilent NetFPGA-10G", 0x1, 0, d, da, True, 0],
        [0x02000151, "Arty", "Digilent Arty", 0x1, 0, d, da, True, 500],
        [0x01500157, "DSDB", "Digilent DSDB", 0x1, 0, d, da, True, 0],
        [0x01b00151, "CmodA7", "Digilent Cmod A7", 0x1, 0, d, da, True, 500],
        [0x01700157, "PYNQ", "Digilent PYNQ", 0x1, 0, d, da, True, 0],
    ]:
    setattr(FtdiSerial, un, FtdiSerial(man, desc, "", has_b, power,
                                       Serial(0, pd, un, pd, dpu, dpr)))

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
