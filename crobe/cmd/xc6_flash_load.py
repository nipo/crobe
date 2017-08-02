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

        def c26_erase_declare(self):
            self.parser.add_argument('--erase-all', action = "store_true",
                                     help = "Erase all chip")

        def c26_erase_parse(self, args):
            self.erase_all = args.erase_all
            
        forced_interface = "jtag"
        program_count_needed = 1
        max_freq = 40e6

    args = Tool("XC6S Flash loader")

    args.interface.start()
    fpga, = args.interface.children_of_class(Spartan6)

    spi = fpga.spi_interface()
    spi.start()

    flash = SpiFlash.detect(spi)

    if args.erase_all:
        flash.erase_all()
    
    with TimedLogger(logging, "writing flash"):
        flash.write(args.program, verify = args.check, erase_first = not args.erase_all)
    
if __name__ == '__main__':
    main()
