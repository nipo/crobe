import logging
import struct
from ..target.soc.model import SoC
from ..component.model import Cpu

def main():
    from . import base

    class Tool(base.Speed, base.Power, base.IcePick, base.Field, base.Programs):
        pass

    args = Tool("File loader")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Nickname:", args.interface.port.nickname)
    print("Speed:", args.interface.speed)

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


