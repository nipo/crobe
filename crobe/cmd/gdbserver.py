import logging
import struct
from ..bitstring import BitString
from ..util.socket_server import *
from ..util.pretty import metric
from ..target.soc.model import SoC
from ..target.soc.gdb import Responder

class GdbServer(SocketServer):
    def __init__(self, port, soc):
        SocketServer.__init__(self, port)
        self.soc = soc

    def spawn(self, socket):
        return Responder(socket, self.soc)
        
def main():
    from . import base

    class Tool(base.Field):
        expected_target = SoC

        def c32_port_declare(self):
            self.parser.add_argument('--port', '-P', type = int, default = 2331,
                                         help = "TCP port to listen on")

        def c32_port_parse(self, args):
            self.port = args.port

    args = Tool("GDB Server")

    try:
        args.interface.reset = False
    except NotImplementedError:
        pass

    print("SoC under control:", args.target)
    
    GdbServer(args.port, args.target).serve()

if __name__ == '__main__':
    main()


