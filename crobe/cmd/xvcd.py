from ..util.pretty import metric

def main():
    from . import base
    from ..adapter.protocol.jtag import Interface
    from ..xvcd.server import XvcdServer

    class Tool(base.Root):
        def c32_port_declare(self):
            self.parser.add_argument('--port', '-p', type = int, default = 2542,
                                         help = "TCP port to listen on")

        def c32_port_parse(self, args):
            self.port = args.port

    args = Tool("XVCD Server")

    intf = args.roots[0]

    if not isinstance(intf, Interface):
        raise ValueError("Expected a JTAG interface. Try -e [adapter]/jtag.")
    
    print("Adapter:", intf.port.firmware_info)
    print("Serial:", intf.port.serial_number)
    print("Freq:", metric(intf.freq, "Hz"))

    try:
        intf.reset = False
    except NotImplementedError:
        pass
    XvcdServer(args.port, intf).serve()

    
if __name__ == '__main__':
    main()


