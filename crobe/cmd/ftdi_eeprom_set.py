import struct

class FtdiEeprom:
    
    def c50_ftdi_declare(self):
        self.parser.add_argument("--vid", type = str, required = True, default = None, help = "Vendor ID")
        self.parser.add_argument("--pid", type = str, required = True, default = None, help = "Product ID")
        self.parser.add_argument("--version", type = str, required = True, default = "0100", help = "Product version")
        self.parser.add_argument("--vendor", type = str, required = True, default = None, help = "Vendor name")
        self.parser.add_argument("--product", type = str, required = True, default = None, help = "Product name")
        self.parser.add_argument("--serial", type = str, required = True, help = "Serial number")
        self.parser.add_argument("--power", type = int, default = 500, help = "Power drain, mA (0 = self)")
        self.parser.add_argument("--mode", type = str, help = "Port modes (UART, FIFO, CPU, OPTO), comma separated",
                                 default = "FIFO,FIFO")

    def c50_ftdi_parse(self, args):
        self.vendor = args.vendor.encode('ascii', 'ignore')
        self.product = args.product.encode('ascii', 'ignore')
        self.serial = args.serial.encode('ascii', 'ignore')
        self.mode_a, self.mode_b = map(str.upper, args.mode.split(',', 1))
        self.vid = int(args.vid, 16)
        self.pid = int(args.pid, 16)
        self.version = int(args.version, 16)
        self.power = args.power or None
            
def main():
    from . import base
    from ..adapter.ftdi.ftdi import FtdiError, Handle
    from ..adapter.ftdi import api
    import binascii

    class Tool(base.Command, FtdiEeprom):
        def c10_connid_declare(self):
            self.parser.add_argument('--connection', '-c', type = str,
                                     help = "USB Connection ID pair in bus/device format (e.g. 001/035)")

        def c10_connid_parse(self, args):
            self.connection_id = args.connection.encode("ascii")
            
    args = Tool("FTDI EEPROM Writer")

    handle = Handle(args.connection_id, "A", "RESET")

    handle.eeprom_strings_set(args.vendor, args.product, args.serial)
    handle.eeprom_vpv_set(args.vid, args.pid, args.version)
    handle.eeprom_power_set(args.power)
    handle.eeprom_channel_mode_set(args.mode_a, args.mode_b)
    
    for name in sorted(api.EEPROM_VALUE):
        try:
            print("%-20s %s" % (name, handle.eeprom_value_get(name)))
        except FtdiError:
            pass

    ret = input("Write those values ? [n]")
    if ret.lower() != "y":
        print("Cancelled")
        return

    handle.eeprom_writeback()

    print("Replug device for reenumeration")
        
if __name__ == '__main__':
    main()
