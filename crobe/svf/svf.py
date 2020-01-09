from ..bitstring import BitString
import re

__doc__ = """Serial Vector Format parser."""

class Token:
    def __init__(self, filename, line, column, text):
        self.filename = filename
        self.line = line
        self.column = column
        self.text = text

    def line_info(self):
        return "%s:%s:%s" % (self.filename, self.line, self.column)
        
class Lexer:
    splitter = re.compile(r'([\t \(\);!]|//)')
    def __init__(self, fd_or_filename, filename = "<svf>"):
        try:
            fd_or_filename.read
            self.fd = fd_or_filename
            self.filename = filename
            return
        except Exception as e:
            pass
        self.filename = fd_or_filename
        self.fd = open(fd_or_filename, "rb")

    def __iter__(self):
        for lineno, line in enumerate(self.fd.readlines()):
            s_line = str(line, "utf-8", "ignore")
            line = s_line.lstrip()
            column = len(s_line) - len(line)
            line = line.rstrip()

            tokens = self.splitter.split(line)

            for t in tokens:
                if not t or t  == " " or t == "\t":
                    column += len(t)
                    continue

                if t in ("//", "!"):
                    break

                yield Token(self.filename, lineno+1, column, t)
                column += len(t)

class Statement:
    def __init__(self, token):
        self.__token = token

    def line_info(self):
        return self.__token.line_info()

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__,
                           ", ".join(map("%s = %r".__mod__, self.__dict__.items())))

class EndState(Statement):
    def __init__(self, token, end_state):
        super().__init__(token)
        end_state = end_state.lower()
        assert end_state in Parser.STABLE_STATES
        self.end_state = end_state

class EndIr(EndState):
    pass

class EndDr(EndState):
    pass

class Trst(Statement):
    def __init__(self, token, value):
        super().__init__(token)
        value = value.lower()
        assert value in ("on", "off", "z", "absent")
        self.value = value

class Frequency(Statement):
    def __init__(self, token, value):
        super().__init__(token)
        self.value = float(value.lower())

class State(Statement):
    def __init__(self, token, states):
        super().__init__(token)
        self.states = states

class Shift(Statement):
    def __init__(self, token, tdi = None, tdo = None, mask = None, smask = None):
        super().__init__(token)
        self.tdi = tdi

        if mask and not int(mask):
            tdo = None
            mask = None

        self.tdo = tdo

        if mask:
            self.mask = mask
        elif tdo:
            self.mask = BitString(-1, len(tdo))
        else:
            self.mask = None
        self.smask = smask

class TrailerDr(Shift): pass
class TrailerIr(Shift): pass
class HeaderDr(Shift): pass
class HeaderIr(Shift): pass
class ShiftDr(Shift): pass
class ShiftIr(Shift): pass

class RunTest(Statement):
    def __init__(self, token,
                 run_state = None, run_count = None, run_clock = None,
                 min_time = None, max_time = None, end_state = None,
                 tck = None):
        super().__init__(token)
        self.run_state = run_state
        self.run_count = run_count
        self.run_clock = run_clock
        self.min_time = min_time
        self.max_time = max_time
        self.end_state = end_state
        self.tck = tck

class Parser:
    STABLE_STATES = ("reset", "irpause", "drpause", "idle")
    STATES = ("reset",
              "irpause", "ircapture", "irselect", "irshift", "irexit1", "irexit2", "irupdate",
              "drpause", "drcapture", "drselect", "drshift", "drexit1", "drexit2", "drupdate",
              "idle", )

    def __init__(self, filename):
        self.lex = iter(Lexer(filename))

    def __iter__(self):
        while True:
            token = next(self.lex)

            handler = getattr(self, "handle_" + token.text.lower())
            yield handler(token)

    def expect(self, text):
        t = next(self.lex)
        if t.text.lower() == text:
            return
        raise ValueError("%s: Expected '%s', had '%s'" % (t.line_info(), text, t.text))
            
    def handle_enddr(self, token):
        end_state = next(self.lex)
        self.expect(";")
        return EndDr(token, end_state.text)

    def handle_endir(self, token):
        end_state = next(self.lex)
        self.expect(";")
        return EndIr(token, end_state.text)

    def handle_trst(self, token):
        value = next(self.lex)
        self.expect(";")
        return Trst(token, value.text)

    def handle_frequency(self, token):
        freq = next(self.lex)
        if freq.text == ";":
            return Frequency(token)
        self.expect("hz")
        self.expect(";")
        return Frequency(token, freq.text)

    def handle_state(self, token):
        states = []
        while True:
            st = next(self.lex)
            if st.text == ";":
                break
            s = st.text.lower()
            assert s in self.STATES
            states.append(s)
        return State(token, states)

    def handle_tir(self, token):
        return self.handle_shift(token, TrailerIr)
    def handle_tdr(self, token):
        return self.handle_shift(token, TrailerDr)
    def handle_hir(self, token):
        return self.handle_shift(token, HeaderIr)
    def handle_hdr(self, token):
        return self.handle_shift(token, HeaderDr)
    def handle_sir(self, token):
        return self.handle_shift(token, ShiftIr)
    def handle_sdr(self, token):
        return self.handle_shift(token, ShiftDr)

    def handle_shift(self, token, shift_class):
        length = int(next(self.lex).text)
        fields = dict(
            tdi = None,
            tdo = None,
            mask = None,
            smask = None,
            )

        while True:
            tok = next(self.lex)
            if tok.text == ";":
                return shift_class(token, **fields)

            tok = tok.text.lower()
            assert tok in fields
            assert fields[tok] is None

            self.expect("(")
            data = next(self.lex).text
            while True:
                n = next(self.lex)
                if n.text == ")":
                    break
                data += n.text

            fields[tok] = BitString(int("0x"+data, 16), length)

    def handle_pio(self, token):
        return self.unsupported(token)

    def handle_piomap(self, token):
        return self.unsupported(token)

    def unsupported(self, token):
        while next(self.lex).text != ';':
            continue

    def handle_runtest(self, token):
        n = next(self.lex).text.lower()
        args = dict()

        if n in self.STABLE_STATES:
            args["run_state"] = n
            n = next(self.lex).text.lower()
        spec = next(self.lex).text.lower()

        if spec == "tck":
            args["tck"] = int(n)
            n = next(self.lex).text.lower()
            if n == ";":
                return RunTest(token, **args)
            spec = next(self.lex).text.lower()

        if spec == "sec":
            args["min_time"] = float(n)
            n = next(self.lex).text.lower()
        else:
            args["run_count"] = int(n)
            args["run_clock"] = spec
            n = next(self.lex).text.lower()

            if n == ";":
                return RunTest(token, **args)

            if n not in ("maximum", "endstate"):
                args["min_time"] = n
                assert next(self.lex).text.lower() == "sec"

        if n == ";":
            return RunTest(token, **args)

        if n == "maximum":
            args["max_time"] = next(self.lex).text.lower()
            assert next(self.lex).text.lower() == "sec"
            n = next(self.lex).text.lower()

        if n == "endstate":
            args["endstate"] = next(self.lex).text.lower()
            n = next(self.lex).text.lower()

        assert n == ";"

        return RunTest(token, **args)




def main():
    import sys

    for statement in Parser(sys.argv[1]):
        print(statement)

if __name__ == '__main__':
    main()
