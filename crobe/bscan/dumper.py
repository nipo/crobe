from ..bitstring import BitString
from ..bsdl.cache import Cache
from ..protocol import jtag
import time
import logging

class Dumper:
    def __init__(self, interface, packages):
        self.packages = packages
        self.logger = logging.getLogger("bsdl")

        assert isinstance(interface, (jtag.Interface, jtag.Tap))
        only = None
        if isinstance(interface, jtag.Tap):
            tap = interface
            chain = tap.port
            interface = chain.port
            only = tap
            taps = [tap]
        else:
            interface.start()
            chain = interface.child_summon("chain")
            chain.child_summon("0")
            taps = chain.children[:]
        self.interface = interface

        cache = Cache.open()

        self.definitions = []

        for index, tap in enumerate(taps):
            try:
                pkg = packages[index]
            except:
                pkg = ""

            d = cache.filter(name = tap.name.lower() if tap.idcode is None else None,
                             idcode = int(tap.idcode) if tap.idcode is not None else None,
                             package = pkg)
            self.logger.info("For TAP #%d, %s %s %s: %s",
                             index,
                             tap.name.lower() if tap.idcode is None else None,
                             hex(int(tap.idcode)) if tap.idcode is not None else None,
                             pkg, d)
            for e in d:
                self.logger.info("%s %s %s %s", e.name, e.id_codes, e.package_variant, e.user_codes)

            if not d:
                self.logger.warn("No BSDL entry for %s", tap.idcode)

            if not d or pkg == "ign" or (only is not None and only is not tap):
                self.definitions.append((None, tap))
                continue

            if len(d) > 1:
                raise KeyError("Ambiguity for part at index %d (%s), choose among packages: %s"
                               % (index, tap.idcode, ",".join(x.package_variant for x in d)))
            
            self.definitions.append((d[0], tap))

        self.sample = BitString()
        self.bs_len = 0
        for d, tap in self.definitions:
            if d:
                self.sample += BitString(d.instructions['sample'].opcodes[0].value,
                                         d.ir_length)
                self.bs_len += d.registers["boundary"].length
            else:
                self.sample += BitString(-1, tap.irlen)
                self.bs_len += 1

    def run(self, ignores = set()):
        try:
            self._run(ignores)
        except KeyboardInterrupt:
            pass

    def _run(self, ignores = set()):
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
                    print(" %s/%s (%s): %d" % (chip, pin.label, pin.name, value))
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
        for d, tap in self.definitions:
            if d:
                chip = {}
                for (name, index), pin in sorted(d.pins.items()):
                    try:
                        ic = d.pin_input_cell[pin]
                    except:
                        continue
                    chip[pin] = bs[offset + ic.number]
                ret[d.name] = chip
                offset += d.registers["boundary"].length
            else:
                offset += 1
        return ret
