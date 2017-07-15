import argparse
import binascii
from datetime import timedelta, datetime
import logging

class RelativeFormatter(logging.Formatter):
    def __init__(self):
        logging.Formatter.__init__(self,
                                   '%(asctime)-15s %(name)-10s %(message)s',
                                   None, "%")
        self.start = datetime.now()

    def formatTime(self, record, datefmt = None):
        elapsed = datetime.now() - self.start
        return str(elapsed)

class Command:
    def __init__(self, help):
        import inspect
        self.parser = argparse.ArgumentParser(description = help)
        for name, hook in sorted(inspect.getmembers(self, predicate = inspect.ismethod)):
            if not name.endswith("_declare"):
                continue
            hook()

        args = self.parser.parse_args()
        for name, hook in sorted(inspect.getmembers(self, predicate = inspect.ismethod)):
            if not name.endswith("_parse"):
                continue
            hook(args)

    def c00_verbose_declare(self):
        self.parser.add_argument('-v', action='count', default = 1,
                                 help = "Increase verbosity (Error -> Warning -> Info -> Debug)")
        self.parser.add_argument('-q', action='count', default = 0,
                                 help = "Decrease verbosity (Error <- Warning <- Info <- Debug)")

    def c00_verbose_parse(self, args):
        handler = logging.StreamHandler()
        formatter = RelativeFormatter()
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(10 * (5 - args.v + args.q))

        root.info("Starting at %s", formatter.start)

class Adapter(Command):
    def c10_adapter_declare(self):
        self.parser.add_argument('--adapter', '-a', type = str, default = "0",
                                 help = "Adapter identifier or index (use crobe.cmd.adapters for a list)")

    def c10_adapter_parse(self, args):
        from ..adapter.model import Enumerator, Adapter

        Enumerator.singleton.start()

        self.adapter = Enumerator.singleton.get(args.adapter)
    
class Interface(Adapter):
    forced_interface = None

    def c20_interface_declare(self):
        if not self.forced_interface:
            self.parser.add_argument('--interface', '-i', type = str, default = "swd",
                                     help = "Target insterface")

    def c20_interface_parse(self, args):
        interface = self.forced_interface or args.interface
        self.interface = self.adapter.open(interface)

class Freq(Interface):
    def c30_freq_declare(self):
        self.parser.add_argument('--freq', '-f', type = str, default = "10e6",
                                     help = "Target insterface freq (Hz)")

    def c30_freq_parse(self, args):
        from ..util.pretty import sci_parse
        self.interface.freq = sci_parse(args.freq)
    
class Power(Interface):
    def c24_power_declare(self):
        self.parser.add_argument('--power', '-p', type = str, default = "",
                                     help = "Target power (untouched if not specified)")

    def c24_power_parse(self, args):
        import time
        if args.power:
            self.interface.power = args.power.lower() in ["on", "1", "true"]
            time.sleep(.05)
    
class IcePick(Interface):
    def c25_icepick_declare(self):
        self.parser.add_argument('--icepick', action = "store_true",
                                 help = "Use ICEPick initialization sequence (requires JTAG)")

    def c25_icepick_parse(self, args):
        self.interface.use_icepick = args.icepick

class Programs:
    program_count_needed = None

    def c40_program_declare(self):
        if self.program_count_needed is None:
            self.parser.add_argument('programs', metavar = 'PROGRAMS',
                                     type = str, nargs = '*',
                                     help = 'Files to load')
        else:
            self.parser.add_argument('programs', metavar = 'PROGRAM',
                                     type = str, nargs = self.program_count_needed,
                                     help = 'File to load')

    def c40_program_parse(self, args):
        from ..loadable.object import Program
        self.program = Program()

        for fn in args.programs:
            try:
                filename, offset = fn.split("+", 1)
                offset = int(offset, 16)
                assert os.path.exists(filename)
            except:
                filename = fn
                offset = 0

            prog = Program.from_file(filename, offset)

            self.program += prog

class File:
    def c50_file_declare(self):
        self.parser.add_argument('file', metavar = 'FILE',
                                 type = str, nargs = 1,
                                 help = 'File to load')

    def c50_file_parse(self, args):
        from ..loadable.object import Program
        self.file = args.file[0]

class Field(Interface):
    def c60_field_parse(self, args):
        self.interface.start()

        from ..target.model import Field

        self.field = Field()
        self.field.discover(self.interface)

if __name__ == "__main__":
    class LolCommand:
        def __init__(self):
            pass

        def lol_declare(self):
            print("lol")

    class Test(Command, LolCommand):
        pass

    args = Test()
