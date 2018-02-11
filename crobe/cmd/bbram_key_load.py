import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..util.pretty import metric
from ..util.info import TimedLogger
from ..target.memory import Loadable

def main():
    from . import base

    class Tool(base.Target):
        def c25_key_declare(self):
            self.parser.add_argument('key', type = str,
                                     help = "BBRAM key")

        def c25_check_parse(self, args):
            self.key = int(args.key, 16)

    args = Tool("BBRAM key loader")
    assert isinstance(args.target, Loadable)

    print("Target:", args.target)

    args.target.component.bbram_open()
    args.target.component.bbram_key_write(args.key)
    assert args.key == args.target.component.bbram_key_read()
    args.target.component.bbram_close()

if __name__ == '__main__':
    import sys
    sys.exit(main())



