import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..util.pretty import sci

def main():
    from . import base

    class Tool(base.Freq, base.Power, base.IcePick, base.Field, base.Programs):
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


    args = Tool("File loader")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Nickname:", args.interface.port.nickname)
    print("Freq:", sci(args.interface.freq, "Hz"))

    soc, = args.field.children_of_class(SoC)
    cpu, = soc.children_of_class(Cpu)

    print("Target:", soc)

    try:
        args.interface.reset = False
    except NotImplementedError:
        pass

    if args.erase_all:
        print("Erasing all...", end = "", flush = True)
        soc.erase_all()
        print(" done")
    
    print("Writing flash...", end = "", flush = True)
    soc.load(args.program, erase = not args.erase_all)
    print(" done")

    if args.check:
        print("Checking...", end = "", flush = True)
        ok = soc.verify(args.program)
        print(" done" if ok else " FAIL")
        if not ok:
            return 1
        
    cpu.reset()
    cpu.resume()

if __name__ == '__main__':
    import sys
    sys.exit(main())



