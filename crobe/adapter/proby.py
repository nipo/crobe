from . import model
from .ftdi.basic import JtagAdapterEnumerator, Adapter, JtagInterface
from ..loadable.object import Program
import os
import os.path
import time

__all__ = []

class ProbyAdapter(Adapter):
    base_path = os.path.join(os.path.dirname(__file__), "proby-fw")

    def __init__(self, enumerator, device):
        Adapter.__init__(self, enumerator, device)
        self.supported_interfaces = ["jtag"]
        self.mode = None

    def open(self, interface_name):
        self.reprogram(interface_name)

        if interface_name == "jtag":
            return Adapter.open(self, "jtag", channel = "A", resetn_pin = 9, activity_pin = 4)

    def reprogram(self, mode):
        from ..component.fpga.spartan6 import Spartan6

        self.logger.info("Reprogramming FPGA to use mode %s", mode)

        if self.mode == mode:
            self.logger.info("Already in mode %s, doing nothing", self.mode)
            return

        filename = os.path.join(self.base_path, mode + ".bit.gz")

        self.logger.info("Using internal chain of Proby, starting discovery")

        jtag_intf = Adapter.open(self, "jtag", channel = "B", resetn_pin = 9)
        jtag_intf.speed = 30e6
        jtag_intf.start()
        fpga, = jtag_intf.children_of_class(Spartan6)

        self.logger.info("Got FPGA in chain: %s", fpga)

        obj = Program.from_file(filename)

        fpga.load(obj)

        for i in range(10):
            done = jtag_intf.handle.gpio_get(5)
            if done:
                break
            time.sleep(.01)

        if not done:
            raise RuntimeError("FPGA not done, timeout")

        self.mode = mode

        del jtag_intf

@model.Enumerator.register
class Enumerator(JtagAdapterEnumerator):
    adapter_class = ProbyAdapter

    def __init__(self):
        JtagAdapterEnumerator.__init__(self, "Proby", "proby",
                                       vid = 0x10eb, pid = 0x0026)

    def serial_mangle(self, serial):
        return serial.split(";")[-1]

@model.Enumerator.register
class Enumerator(JtagAdapterEnumerator):
    def __init__(self):
        JtagAdapterEnumerator.__init__(self, "Proby-internal", "proby-int",
                                       vid = 0x10eb, pid = 0x0026,
                                       channel = "B",
                                       resetn_pin = 9)

    def serial_mangle(self, serial):
        return serial.split(";")[-1]
