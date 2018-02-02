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

            self.parser.add_argument('size', metavar = 'size',
                                     type = int,
                                     default = 4,
                                     help = 'Number of bytes to peek')

        def c80_address_parse(self, args):
            self.address = int(args.address, 16)
            self.size = args.size

    args = Tool("Read arbitrary memory address")

    print("Bus:", args.bus)

    data = args.bus.mem_read(args.address, args.size)
    print(hex(args.address), binascii.b2a_hex(data))
    
if __name__ == '__main__':
    import sys
    sys.exit(main())



