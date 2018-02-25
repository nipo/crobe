import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..util.pretty import metric
from ..util.info import TimedLogger
from ..target.memory import Loadable

def main():
    from . import base

    class Tool(base.Target, base.Programs):
        def c25_check_declare(self):
            self.parser.add_argument('--check', action = "store_true",
                                     help = "Read back flash contents and check for equality")
            self.parser.add_argument('--erase-all', action = "store_true",
                                     help = "Erase all chip")
            self.parser.add_argument('--run', action = "store_true",
                                     help = "Reset target afterwards")

        def c25_check_parse(self, args):
            self.check = args.check
            self.erase_all = args.erase_all
            self.run = args.run

    args = Tool("File loader")
    assert isinstance(args.target, Loadable)
    
    print("Target:", args.target)

    if args.erase_all:
        with TimedLogger(logging, "erase all"):
            args.target.erase_all()
    
    if args.program:
        with TimedLogger(logging, "write"):
            args.target.write(args.program)

    if args.check:
        with TimedLogger(logging, "check"):
            ok = args.target.verify(args.program)
            if not ok:
                return 1

    if args.run:
        try:
            args.target.reset()
        except AttributeError:
            print("WARNING: Target does not handle reset")

if __name__ == '__main__':
    import sys
    sys.exit(main())



