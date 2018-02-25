import logging
import struct
import binascii

def main():
    from . import base

    class Tool(base.Bus):
        def c80_address_declare(self):
            self.parser.add_argument('--raw', metavar = 'ADDRESS=DATA',
                                     type = str, action = "append", default = [],
                                     help = 'Blob write')

            self.parser.add_argument('--reg32', metavar = 'ADDRESS=VALUE',
                                     type = str, action = "append", default = [],
                                     help = 'Register to poke')

        def c80_address_parse(self, args):
            self.to_write = []

            print(args.raw, args.reg32)

            for item in args.raw or []:
                address, value = item.split("=", 1)
                address = int(address, 16)
                data = binascii.a2b_hex(value.replace(" ", ""))
                self.to_write.append((address, data))

            for item in args.reg32 or []:
                address, value = item.split("=", 1)
                address = int(address, 16)
                data = struct.pack("<L", int(value, 16))
                self.to_write.append((address, data))

    args = Tool("Write arbitrary memory address")

    print("Bus:", args.bus)

    for address, data in args.to_write:
        print("0x%08x: %s" % (address, binascii.b2a_hex(data)))
        args.bus.mem_write(address, data)
    
if __name__ == '__main__':
    import sys
    sys.exit(main())



