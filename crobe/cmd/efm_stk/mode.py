from .. import base
from ...adapter.jlink import Adapter
from ...component.energy_micro.stk import *

def main():
    class Tool(base.Root):
        def c20_mode_declare(self):
            self.parser.add_argument("mode", metavar = "MODE",
                                     type = str, default = "",
                                     nargs = "?",
                                     help = "MCU mode")

        def c20_mode_parse(self, args):
            self.mode = args.mode

    args = Tool("EFM32 STK debug mode tool")

    jlink = args.root
    assert isinstance(jlink, Adapter)

    for i in jlink.supported_interfaces:
        try:
            interface = jlink.open(i)
        except NotImplementedError:
            continue

        stk = EfmStk(interface)

        print("Current mode:", stk.debug_mode)

        if args.mode:
            print("Changing to:", args.mode)
            stk.debug_mode = args.mode

if __name__ == '__main__':
    main()


