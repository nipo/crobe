from . import model
from .ftdi import basic, ftdi

__all__ = []

class Adapter(basic.Adapter):
    supported_interfaces = ["jtag", "swd", "jtag-int"]

    def open(self, interface_name):
        if interface_name == "jtag":
            return basic.Adapter.open(self, interface_name,
                                      gpio_output = 0x7c2d, gpio_value = 0x0c20,
                                       channel = "A",
                                       resetn_pin = 11,
                                       activity_pin = 15)
        elif interface_name == "jtag-int":
            return basic.Adapter.open(self, "jtag", channel = "B")
        elif interface_name == "swd":
            return basic.Adapter.open(self, interface_name,
                                      oen_pin = 12,
                                      gpio_output = 0x7c25, gpio_value = 0x0c00,
                                       channel = "A",
                                       resetn_pin = 11,
                                       activity_pin = 15)

@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    """This enumerator autodetects Busblaster in KT-Prog mode as explained
    in the Readme file accompagnying busblaster CPLD firmware.

    You can also invoke it explicitly using any of the following:
    - "busblaster/vid:pid/protocol"
    - "busblaster/vid:pid@conn_id/protocol"
    as explicit connection string.

    conn_id must be "bus_num:dev_num" with both numbers in 3-digit
    decimal, as used by libusb.
    """
    adapter_class = Adapter

    def __init__(self):
        basic.AdapterEnumerator.__init__(self, "Busblaster",
                                       short_name = "bb",
                                       vid = 0x0403, pid = 0x8878)

    def child_spawn(self, name):
        try:
            vid_pid, conn = name.split('@')
            conn = conn.replace(":", "/")
        except:
            vid_pid = name
            conn = None

        vid, pid = name.split(':', 1)
        vid = int(vid, 16)
        pid = int(pid, 16)

        devices = ftdi.Device.list_all(vid, pid)
        if conn is not None:
            devices = [d for d in devices if conn in d.connection_id]
        if len(devices) == 1:
            return self.adapter_class(self, devices[0])
