import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..util.pretty import metric
from ..util.info import TimedLogger
from ..target.memory import Loadable, Region, Flash
from ..loadable.object import Program, Segment

def main():
    from . import base

    class Tool(base.Target, base.File):
        pass

    args = Tool("Read memory based chip back to data file")

    assert isinstance(args.target, (Loadable, Region))

    print("Target:", args.target)

    p = Program()
    for memory in args.target.children_of_class(Region):
        cs = 1024

        if isinstance(memory, Flash):
            cs = memory.page_size
        
        blob = bytearray()
        for offset in range(0, memory.size, cs):
            with TimedLogger(logging, "read at %08x (%d%%)" % (offset, offset / memory.size * 100)):
                blob += memory.read(offset, cs)

        p.append(Segment(memory.address, blob))

    p.save(args.file)
    
if __name__ == '__main__':
    import sys
    sys.exit(main())



