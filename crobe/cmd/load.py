import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..util.pretty import metric
from ..util.info import TimedLogger

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

    soc, = args.field.children_of_class(SoC)
    cpu, = soc.children_of_class(Cpu)

    print("Target:", soc)

    try:
        args.interface.reset = False
    except NotImplementedError:
        pass

    if args.erase_all:
        with TimedLogger(logging, "erasing all"):
            soc.erase_all()
    
    with TimedLogger(logging, "writing flash"):
        soc.load(args.program, erase = not args.erase_all)

    if args.check:
        with TimedLogger(logging, "checking flash"):
            ok = soc.verify(args.program)
            if not ok:
                return 1
        
    cpu.reset()
    cpu.resume()

if __name__ == '__main__':
    import sys
    sys.exit(main())



