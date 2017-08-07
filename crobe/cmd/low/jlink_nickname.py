def main():
    from .. import base
    from ...adapter.jlink import Adapter
    import binascii

    class Tool(base.Root):
        def c20_name_declare(self):
            self.parser.add_argument("nickname", metavar = "NICKNAME",
                                     type = str, default = "",
                                     help = "New JLink nickname")

        def c20_name_parse(self, args):
            self.nickname = args.nickname

    args = Tool("JLink nickname changer")

    jlink = args.roots[0]
    assert isinstance(jlink, Adapter)

    for i in ["swd", "jtag"]:
        try:
            interface = jlink.open(i)
        except NotImplementedError:
            continue

        interface.handle.nickname = args.nickname

        return

if __name__ == '__main__':
    main()


