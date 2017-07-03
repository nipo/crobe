from ..util.pretty import sci

def main():
    from . import base
    
    class Tool(base.Freq, base.Power, base.IcePick, base.Field):
        def c25_cpuid_declare(self):
            self.parser.add_argument('--cpuid', action = "store_true",
                                     help = "Dump CPUID capabilities")

        def c25_cpuid_parse(self, args):
            self.cpuid = args.cpuid

    args = Tool("Target enumerator")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Nickname:", args.interface.port.nickname)
    print("Freq:", sci(args.interface.freq, "Hz"))
    
    component_dump(args.interface)
    component_dump(args.field)

    if args.cpuid:
        from ..component.arm.cpuid import CpuidDumper
        from ..component.arm.cortex import Cortex
        cortexes = args.field.children_of_class(Cortex)
        for c in cortexes:
            CpuidDumper(c.scs).dump(print)
    
def component_dump(comp, prefix = ""):
    print(prefix, comp)
    for c in comp.children:
        component_dump(c, prefix + "  ")
    
if __name__ == '__main__':
    main()


