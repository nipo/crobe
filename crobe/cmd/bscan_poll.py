from ..bsdl.cache import Cache
from ..part_id import PartId
from ..bitstring import BitString
from ..adapter.protocol import jtag
import time

class BsDumper:
    def __init__(self, interface, packages):
        self.interface = interface
        self.packages = packages

        assert isinstance(interface, jtag.Interface)
        chain = interface.children[0]
        taps = chain.children[:]

        cache = Cache.open()

        self.definitions = []

        for index, tap in enumerate(taps):
            try:
                pkg = packages[index]
            except:
                pkg = ""

            d = cache.filter(idcode = int(tap.idcode), package = pkg)

            if not d:
                raise KeyError("No BSDL entry for %s" % tap.idcode)
            if len(d) > 1:
                raise KeyError("Ambiguity for part at index %d (%s), choose among packages: %s"
                               % (index, tap.idcode, ",".join(x.package_variant for x in d)))

            self.definitions.append(d[0])

        self.sample = BitString()
        self.bs_len = 0
        for d in self.definitions:
            self.sample += BitString(d.instructions['sample'].opcodes[0].value,
                                     d.ir_length)
            self.bs_len += d.registers["boundary"].length

    def run(self, ignores = set()):
        last_values = self.pin_values()
        last_read = time.time()
        no_change = 0

        while True:
            values = self.pin_values()
            read = time.time()

            diffs = self.differences(last_values, values)

            for i in range(len(diffs)-1, -1, -1):
                chip, pin, value = diffs[i]
                if (chip, pin.label) in ignores:
                    del diffs[i]

            if diffs:
                no_change = 0
                print()
                print("Changes:")
                for chip, pin, value in diffs:
                    print(" %s/%s: %d" % (chip, pin, value))
            else:
                no_change += 1
                print("No change, %d ms interval, %d cycles so far..." % (((read - last_read) * 1000), no_change),
                      end = '\r')

            last_values = values
            last_read = read

    @classmethod
    def differences(cls, last_values, values):
        changed = []

        for chip in sorted(values):
            before = last_values[chip]
            after = values[chip]

            for pin in sorted(before):
                b = before[pin]
                a = after[pin]

                if b != a:
                    changed.append((chip, pin, a))

        return changed

    def pin_values(self):
        shift = self.interface.cmd_shift(BitString(0, self.bs_len), read_tdo = True)
        self.interface.execute([
            self.interface.cmd_capture_ir(),
            self.interface.cmd_shift(self.sample, read_tdo = False),
            self.interface.cmd_capture_dr(),
            shift,
            self.interface.cmd_run(1),
            ])
        bs = shift.tdo

        offset = 0
        ret = {}
        for d in self.definitions:
            chip = {}
            for (name, index), pin in sorted(d.pins.items()):
                try:
                    ic = d.pin_input_cell[pin]
                except:
                    continue
                chip[pin] = bs[offset + ic.number]
            ret[d.name] = chip
            offset += d.registers["boundary"].length
        return ret

def main():
    from . import base
    from ..adapter.protocol import jtag

    class Tool(base.Root):
        expected_root = jtag.Interface

        def c25_package_declare(self):
            self.parser.add_argument("--pkg", help = "Set packages for ICs in chain", type = str, metavar = "PKG,PKG", default = "")
            self.parser.add_argument("--ignore", help = "Ignore some IOs", type = str, metavar = "TAP/PIN,...", default = "")

        def c25_package_parse(self, args):
            self.packages = args.pkg.split(",")
            self.ignore = set()
            for tp in args.ignore.split(','):
                t, p = tp.split("/", 1)
                self.ignore.add((t, p))

    args = Tool("Boundary scan checker")

    dumper = BsDumper(args.roots[0], args.packages)

    try:
        dumper.run(args.ignore)
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
