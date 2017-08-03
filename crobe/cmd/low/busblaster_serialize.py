def main():
    from .. import base
    from ...adapter.ftdi.ftdi import FtdiError, Handle
    from ...adapter.ftdi import api
    import binascii

    class Tool(base.Command):
        def c10_connid_declare(self):
            self.parser.add_argument('--connection', '-c', type = str,
                                     help = "USB Connection ID pair in bus/device format (e.g. 001/035)")

        def c10_connid_parse(self, args):
            self.connection_id = args.connection.encode("ascii")
            
    args = Tool("Busblaster serializer")

    handle = Handle(args.connection_id, "A", "RESET")

    
    try:
        raw = handle.eeprom_get()
        for i in range(0, len(raw), 16):
            print("%02x:  %s" % (i, " ".join(map("%02x".__mod__, raw[i:i+16]))))
    except:
        print("No valid data found in EEPROM")
        return
    
    for name in sorted(api.EEPROM_VALUE):
        try:
            print("%-20s %s" % (name, handle.eeprom_value_get(name)))
        except FtdiError:
            pass
            
if __name__ == '__main__':
    main()


