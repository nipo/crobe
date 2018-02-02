import logging
import struct
import binascii

def main():
    from . import base

    class Tool(base.Bus):
        def c80_address_declare(self):
            self.parser.add_argument('address', metavar = 'ADDRESS',
                                     type = str,
                                     help = 'Address to peek')

            self.parser.add_argument('data', metavar = 'data',
                                     type = str, nargs = 1,
                                     help = 'Data to poke')

        def c80_address_parse(self, args):
            self.address = int(args.address, 16)
            self.data = binascii.a2b_hex(args.data.replace(" ", ""))

    args = Tool("Write arbitrary memory address")

    print("Bus:", args.bus)

    args.bus.mem_write(args.address, args.data)
    
if __name__ == '__main__':
    import sys
    sys.exit(main())



