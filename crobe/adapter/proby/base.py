from .. import model
from ..ftdi import basic
from ...loadable.object import Program
import logging
import os
import os.path
import time

__all__ = ['Reflasher', 'Enumerator']

class Reflasher(object):
    base_path = os.path.join(os.path.dirname(__file__), "fw")

    def reprogram(self, mode):
        """
        Loads a design into proby. Try to optimize not reloading by
        first doing an internal cache of last loaded design, and also
        try to check UserID register with a magic value.
        
        :param str mode: Base name of design bitstream
        """
        from ...component.xilinx.spartan6 import Spartan6

        self.logger.info("Reprogramming FPGA to use mode %s", mode)

        filename = os.path.join(self.base_path, mode + ".bit.gz")
        obj = Program.from_file(filename)

        expected_userid = obj.info.get("userid", None)
        if expected_userid == 0xffffffff:
            expected_userid = None

        if expected_userid:
            self.logger.info("Expected UserID=0x%08x", expected_userid)
                 
        self.logger.info("Using internal chain of Proby, starting discovery")

        jtag_intf = model.Enumerator.singleton.get("int-proby:" + self.serial_number).open("jtag")
        jtag_intf.logger.setLevel(logging.WARNING)
        jtag_intf.freq = 40e6
        jtag_intf.start()
        fpga, = jtag_intf.children_of_class(Spartan6)

        self.logger.info("Got FPGA in chain: %s", fpga)

        if expected_userid:
            userid = fpga.dr_shift(fpga.IR_USERCODE, 0, 32)
            self.logger.info("Current User ID: 0x%08x", userid)
            if userid == expected_userid:
                self.logger.info("UserID matches, doing nothing")
                del jtag_intf
                return

        fpga.load(obj)

        for i in range(10):
            done = jtag_intf.handle.gpio_get(5)
            if done:
                break
            time.sleep(.01)

        if not done:
            raise RuntimeError("FPGA not done, timeout")

        del jtag_intf

class Enumerator(basic.AdapterEnumerator):
    def __init__(self, name, nick, **kwargs):
        basic.AdapterEnumerator.__init__(self, name, nick,
                                        vid = 0x10eb, pid = 0x0026, **kwargs)

    def serial_mangle(self, serial):
        return serial.split(";")[-1]

@model.Enumerator.register
class ProbyIntEnumerator(Enumerator):
    def __init__(self):
        Enumerator.__init__(self, "Proby-internal", "int-proby",
                            channel = "B", resetn_pin = 9)
