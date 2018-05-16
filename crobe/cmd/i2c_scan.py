def main():
    from . import base
    from ..adapter.protocol.i2c import Interface, AddressNack

    class Tool(base.Root):
        def c80_range_declare(self):
            self.parser.add_argument('--first', metavar = 'ADDR',
                                     type = str, default = "1",
                                     help = 'First address to scan')

            self.parser.add_argument('--last', metavar = 'ADDR',
                                     type = str, default = "0x7f",
                                     help = 'Last address to scan (inclusive)')

            self.parser.add_argument('--addr', metavar = 'ADDR',
                                     type = str, action = "append",
                                     help = 'Explicit address to scan')

        def c80_range_parse(self, args):
            first = int(args.first, 16)
            last = int(args.last, 16)
            addresses = list(map(lambda x: int(x, 16), args.addr or []))
            self.addresses = addresses or list(range(first, last + 1))

    args = Tool("I2C Scanner")

    bus = args.roots[0]

    for addr in args.addresses:
        try:
            bus.write(addr, b'')
        except AddressNack:
            continue
        print("Slave on address %02x" % addr)

if __name__ == '__main__':
    main()
