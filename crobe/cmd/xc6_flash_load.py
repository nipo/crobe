import logging
from ..component.xilinx.spartan6 import Spartan6
from ..component.spi_flash import SpiFlash
import binascii
from ..util.info import TimedLogger

def main():
    from . import base

    class Tool(base.Freq, base.Programs):
        def c25_check_declare(self):
            self.parser.add_argument('--check', action = "store_true",
                                     help = "Read back flash contents and check for equality")

        def c25_check_parse(self, args):
            self.check = args.check

        forced_interface = "jtag"
        program_count_needed = 1
        max_freq = 40e6

    args = Tool("XC6S Flash loader")

    args.interface.start()
    fpga, = args.interface.children_of_class(Spartan6)

    spi = fpga.spi_interface()
    spi.start()

    flash = SpiFlash.detect(spi)

    with TimedLogger(logging, "writing flash"):
        flash.write(args.program)

    if args.check:
        with TimedLogger(logging, "checking flash"):
            ok = flash.verify(args.program)
            if not ok:
                logging.error("Check failed")
                return 1
    
if __name__ == '__main__':
    main()
