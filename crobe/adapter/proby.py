from . import model
from .ftdi.basic import JtagAdapterEnumerator, Adapter, JtagInterface
from ..loadable.object import Program
import logging
import os
import os.path
import time

__all__ = []

class ProbyAdapter(Adapter):
    base_path = os.path.join(os.path.dirname(__file__), "proby-fw")
    supported_interfaces = ["jtag", "swd"]

    def __init__(self, enumerator, device):
        Adapter.__init__(self, enumerator, device)
        self.mode = None

    def reprogram(self, mode, design_id = None):
        """
        Loads a design into proby. Try to optimize not reloading by
        first doing an internal cache of last loaded design, and also
        try to check USER1 TAP register with a magic value.
        
        :param str mode: Base name of design bitstream
        :param int design_id: ID magic value to check against USER1
        """
        from ..component.xilinx.spartan6 import Spartan6

        self.logger.info("Reprogramming FPGA to use mode %s", mode)

        if self.mode == mode:
            self.logger.info("Already in mode %s, doing nothing", self.mode)
            return

        self.logger.info("Using internal chain of Proby, starting discovery")

        jtag_intf = Adapter.open(self, "jtag", channel = "B", resetn_pin = 9)
        jtag_intf.logger.setLevel(logging.WARNING)
        jtag_intf.freq = 40e6
        jtag_intf.start()
        fpga, = jtag_intf.children_of_class(Spartan6)

        self.logger.info("Got FPGA in chain: %s", fpga)

        if design_id is not None:
            did = fpga.dr_shift(fpga.IR_USER1, 0, 32)
            self.logger.info("Current design ID: %08x", did)
            if design_id == did:
                self.logger.info("Design ID from USER1 matches, doing nothing")
                del jtag_intf
                return

        filename = os.path.join(self.base_path, mode + ".bit.gz")
        
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

    def open(self, interface_name):
        self.reprogram("jtag_swd_raw", 0xbcc464b8)

        if interface_name == "jtag":
            return Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                activity_pin = 14,
                                gpio_output = 0x061b, gpio_value = 0x0210)
        elif interface_name == "swd":
            return Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                activity_pin = 14,
                                oe_pin = 5,
                                gpio_output = 0x063b, gpio_value = 0x0610)

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
        JtagAdapterEnumerator.__init__(self, "Proby-internal", "int-proby",
                                       vid = 0x10eb, pid = 0x0026,
                                       channel = "B",
                                       resetn_pin = 9)

    def serial_mangle(self, serial):
        return serial.split(";")[-1]
