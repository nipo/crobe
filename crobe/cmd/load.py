import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..util.pretty import sci

def main():
    from . import base

    class Tool(base.Freq, base.Power, base.IcePick, base.Field, base.Programs):
        pass

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
    
    soc.load(args.program)
    cpu.reset()
    cpu.resume()

if __name__ == '__main__':
    main()


