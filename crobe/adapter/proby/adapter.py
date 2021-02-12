from .. import model
from ..ftdi import basic
from ...loadable.object import Program
from ...protocol import base
import logging

__all__ = ['Proby', 'Enumerator']

class FifoInterface(base.Interface):
    def __init__(self, port, name):
        super().__init__(port, name)

    def freq_update(self, freq):
        return 60e6
        
    def read(self, size = None):
        return self.port._read(size)

    def write(self, data):
        return self.port.write(data)

class ProbyAdapter(basic.Adapter):
    supported_interfaces = ["swd", "swd-pt", "jtag", "jtag-raw", "jtag-int", "spi", "spi-inv", "cc", "i2c", "spi-raw", "spi-inv-raw"]
    
    def reprogram(self, mode):
        """
        Loads a design into proby. Try to optimize not reloading by
        first doing an internal cache of last loaded design, and also
        try to check UserID register with a magic value.
        
        :param str mode: Base name of design bitstream
        """
        from ...component.xilinx.spartan6 import Spartan6

        self.logger.info("Reprogramming FPGA to use mode %s", mode)

        from pkg_resources import resource_filename
        fw_name = "fw/" + mode + ".bit.gz"
        fd = resource_filename(__name__, fw_name)

        obj = Program.from_xilinx_bit(fd)
                 
        self.logger.info("Using internal chain of Proby, starting discovery")

        jtag_intf = basic.Adapter.open(self, "jtag", channel = "B", resetn_pin = 9, name = "pint-"+self.serial_number,
                                       gpio_output = 0, gpio_value = 0)
        jtag_intf.logger.setLevel(logging.WARNING)
        jtag_intf.start()
        chain = jtag_intf.child_summon("chain")
        chain.start()
        fpga = chain.child_summon("0")

        self.logger.info("Got FPGA in chain: %s", fpga)

        fpga.load(obj)

    def open(self, interface_name):
        if interface_name in ["jtag", "swd", "i2c", "cc", "spi", "spi-inv"]:
            from .transactors import Meta
            meta = Meta(self, interface_name)
            return meta.interface

        elif interface_name == "jtag-int":
            return basic.Adapter.open(self, "jtag", channel = "B", resetn_pin = 9)

        elif interface_name == "fifo":
            return FifoInterface(
                self.device.open(interface = "A", mode = "ft245_sync_fifo"),
                "fifo")

        elif interface_name == "spi-raw":
            self.reprogram("jtag_swd_raw")
            return basic.Adapter.open(self, interface_name, channel = "A",
                                resetn_pin = 8,
                                csn_pin = 3,
                                gpio_output = 0x061b, gpio_value = 0x0210)

        elif interface_name == "spi-inv-raw":
            self.reprogram("jtag_swapped")
            return basic.Adapter.open(self, "spi", channel = "A",
                                resetn_pin = 8,
                                csn_pin = 3,
                                gpio_output = 0x071b, gpio_value = 0x0210)

        elif interface_name == "jtag-raw":
            self.reprogram("jtag_swd_raw")
            return basic.Adapter.open(self, "jtag", channel = "A",
                                resetn_pin = 8,
                                gpio_output = 0x061b, gpio_value = 0x0210)

        elif interface_name == "swd-pt":
            self.reprogram("jtag_swd_raw")
            return basic.Adapter.open(self, "swd", channel = "A",
                                resetn_pin = 8,
                                oe_pin = 5,
                                gpio_output = 0x063b, gpio_value = 0x0610)

        else:
            raise ValueError("Unknown interface name: %s" % interface_name)
        
@model.HwRoot.register
class Enumerator(basic.AdapterEnumerator):
    adapter_class = ProbyAdapter

    def __init__(self, **kwargs):
        basic.AdapterEnumerator.__init__(self, "Proby", "proby",
                                        vid = 0x10eb, pid = 0x0026, **kwargs)

    def serial_mangle(self, serial):
        return str(int(serial.split(";")[-1]))
