import logging
import struct
from ..bitstring import BitString
from ..util.pretty import metric
from ..target.soc.model import SoC
from ..component.arm.cortex import Cortex
from ..component.arm.coresight.tpiu import Tpiu
from ..component.arm.coresight.etm import Etm

def main():
    from . import base

    class Tool(base.Freq, base.Power, base.IcePick, base.Field):
        pass

    args = Tool("SWO Dumper")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Nickname:", args.interface.port.nickname)
    print("Freq:", metric(args.interface.freq, "Hz"))

    soc, = args.field.children_of_class(SoC)

    try:
        args.interface.reset = False
    except NotImplementedError:
        pass

    print("SoC under control:", soc)

    cpu, = soc.children_of_class(Cortex)
    cpu.halt()
    cpu.reset()

    soc.trace_enable(None, 2e6, True)

    args.interface.swo_start(2e6, 1024)

    cpu.resume(True)
    
    while True:
        buf = args.interface.swo_read(1024)
        if buf:
            print(repr(buf))

if __name__ == '__main__':
    main()


