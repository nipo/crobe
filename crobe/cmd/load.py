import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..util.pretty import metric
from ..util.info import TimedLogger
from ..target.loadable import Loadable

def main():
    from . import base

    class Tool(base.Target, base.Programs):
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
    assert isinstance(args.target, Loadable)
    
    print("Target:", args.target)

    if args.erase_all:
        with TimedLogger(logging, "erasing all"):
            args.target.erase_all()
    
    with TimedLogger(logging, "writing flash"):
        args.target.load(args.program, erase = not args.erase_all)

    if args.check:
        with TimedLogger(logging, "checking flash"):
            ok = args.target.verify(args.program)
            if not ok:
                return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())



