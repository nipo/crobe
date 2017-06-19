from ..bitstring import BitString
import re

__doc__ = """Serial Vector Format parser."""

class SvfLexer:
    splitter = re.compile(r'([ \(\);!]|//)')
    def __init__(self, filename):
        try:
            fd.read
            self.fd = filename
        except:
            self.fd = open(filename, "rb")

    def __iter__(self):
        for line in self.fd.readlines():
            line = str(line.strip(), "utf-8", "ignore")
            tokens = self.splitter.split(line)

            for t in tokens:
                if not t or t  == " ":
                    continue

                if t in ("//", "!"):
                    break

                yield t

class SvfStatement:
    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__,
                           ", ".join(map("%s = %r".__mod__, self.__dict__.items())))

class EndState(SvfStatement):
    def __init__(self, end_state):
        end_state = end_state.lower()
        assert end_state in SvfParser.STABLE_STATES
        self.end_state = end_state

class EndIr(EndState):
    pass

class EndDr(EndState):
    pass

class Trst(SvfStatement):
    def __init__(self, value):
        value = value.lower()
        assert value in ("on", "off", "z", "absent")
        self.value = value

class Frequency(SvfStatement):
    def __init__(self, value):
        self.value = float(value.lower())

class State(SvfStatement):
    def __init__(self, states):
        self.states = states

class Shift(SvfStatement):
    def __init__(self, tdi = None, tdo = None, mask = None, smask = None):
        self.tdi = tdi
        self.tdo = tdo
        self.mask = mask
        self.smask = smask

class TrailerDr(Shift): pass
class TrailerIr(Shift): pass
class HeaderDr(Shift): pass
class HeaderIr(Shift): pass
class ShiftDr(Shift): pass
class ShiftIr(Shift): pass

class RunTest(SvfStatement):
    def __init__(self, run_state = None, run_count = None, run_clock = None,
                 min_time = None, max_time = None, end_state = None):
        self.run_state = run_state
        self.run_count = run_count
        self.run_clock = run_clock
        self.min_time = min_time
        self.max_time = max_time
        self.end_state = end_state

class SvfParser:
    STABLE_STATES = ("reset", "irpause", "drpause", "idle")
    STATES = ("reset",
              "irpause", "ircapture", "irselect", "irshift", "irexit1", "irexit2", "irupdate",
              "drpause", "drcapture", "drselect", "drshift", "drexit1", "drexit2", "drupdate",
              "idle", )

    def __init__(self, filename):
        self.lex = iter(SvfLexer(filename))

    def __iter__(self):
        while True:
            token = next(self.lex)

            handler = getattr(self, "handle_" + token.lower())
            yield handler()

    def handle_enddr(self):
        end_state = next(self.lex)
        assert next(self.lex) == ";"
        return EndDr(end_state)

    def handle_endir(self):
        end_state = next(self.lex)
        assert next(self.lex) == ";"
        return EndIr(end_state)

    def handle_trst(self):
        value = next(self.lex)
        assert next(self.lex) == ";"
        return Trst(value)

    def handle_frequency(self):
        freq = next(self.lex)
        if freq == ";":
            return Frequency()
        assert next(self.lex).lower() == "hz"
        assert next(self.lex) == ";"
        return Frequency(freq)

    def handle_state(self):
        states = []
        while True:
            st = next(self.lex)
            if st == ";":
                break
            states.append(st)
        return State(states)

    def handle_tir(self):
        return self.handle_shift(TrailerIr)
    def handle_tdr(self):
        return self.handle_shift(TrailerDr)
    def handle_hir(self):
        return self.handle_shift(HeaderIr)
    def handle_hdr(self):
        return self.handle_shift(HeaderDr)
    def handle_sir(self):
        return self.handle_shift(ShiftIr)
    def handle_sdr(self):
        return self.handle_shift(ShiftDr)

    def handle_shift(self, shift_class):
        length = int(next(self.lex))
        fields = dict(
            tdi = None,
            tdo = None,
            mask = None,
            smask = None,
            )

        while True:
            tok = next(self.lex)
            if tok == ";":
                return shift_class(**fields)

            tok = tok.lower()
            assert tok in fields
            assert fields[tok] is None

            assert next(self.lex) == "("
            data = next(self.lex)
            while True:
                n = next(self.lex)
                if n == ")":
                    break
                data += n

            fields[tok] = BitString(int("0x"+data, 16), length)

    def handle_pio(self):
        return self.unsupported()

    def handle_piomap(self):
        return self.unsupported()

    def unsupported(self):
        while next(self.lex) != ';':
            continue

    def handle_runtest(self):
        n = next(self.lex).lower()
        args = dict()

        if n in self.STABLE_STATES:
            args["run_state"] = n
            n = next(self.lex).lower()
        spec = next(self.lex).lower()

        if spec == "sec":
            args["min_time"] = int(n)
            n = next(self.lex).lower()
        else:
            args["run_count"] = int(n)
            args["run_clock"] = spec
            n = next(self.lex).lower()

            if n == ";":
                return RunTest(**args)

            if n not in ("maximum", "endstate"):
                args["min_time"] = n
                assert next(self.lex).lower() == "sec"

        if n == ";":
            return RunTest(**args)

        if n == "maximum":
            args["max_time"] = next(self.lex).lower()
            assert next(self.lex).lower() == "sec"
            n = next(self.lex).lower()

        if n == "endstate":
            args["endstate"] = next(self.lex).lower()
            n = next(self.lex).lower()

        assert n == ";"

        return RunTest(**args)




def main():
    import sys

    for statement in SvfParser(sys.argv[1]):
        print(statement)

if __name__ == '__main__':
    main()
