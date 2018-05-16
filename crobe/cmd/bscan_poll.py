from ..protocol import jtag
from ..bscan.dumper import Dumper

def main():
    from . import base

    class Tool(base.Root):
        expected_root = jtag.Interface

        def c25_package_declare(self):
            self.parser.add_argument("--pkg", help = "Set packages for ICs in chain", type = str, metavar = "PKG,PKG", default = "")
            self.parser.add_argument("--ignore", help = "Ignore some IOs", type = str, metavar = "TAP/PIN,...", default = "")

        def c25_package_parse(self, args):
            self.packages = args.pkg.split(",")
            self.ignore = set()
            for tp in filter(None, args.ignore.split(',')):
                t, p = tp.split("/", 1)
                self.ignore.add((t, p))

    args = Tool("Boundary scan checker")

    dumper = Dumper(args.roots[0], args.packages)

    try:
        dumper.run(args.ignore)
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
