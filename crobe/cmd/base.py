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

class Root(Command):
    def c10_root_declare(self):
        self.parser.add_argument('--root', '-r', type = str, default = "0/",
                                 help = "Root name, index")

    def c10_root_parse(self, args):
        from ..adapter.model import Enumerator

        Enumerator.singleton.start()

        parts = args.root.split("/")
        
        self.root = Enumerator.singleton.child_summon(*parts)

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
            if len(args.programs) == 1:
                self.program = prog
                break

            self.program += prog

class Field(Root):
    def c60_field_parse(self, args):
        from ..target.model import Field

        self.field = Field()
        self.field.discover(self.root)

class Target(Field):
    def c61_target_declare(self):
        self.parser.add_argument('--target', '-t', metavar = 'NAME',
                                 type = str, default = "0",
                                 help = 'Target accessor')

    @staticmethod
    def _predicate(child, target):
        return target in child.name.lower()
        
    def c61_target_parse(self, args):
        from ..target.model import Field

        try:
            idx = int(args.target)
            self.target = self.field.children[idx]
        except:
            self.target = self.field.child_get(lambda x: self._name_predicate(x, args.target.lower()))

class File:
    def c50_file_declare(self):
        self.parser.add_argument('file', metavar = 'FILE',
                                 type = str, nargs = 1,
                                 help = 'File to load')

    def c50_file_parse(self, args):
        self.file = args.file[0]

class ConnectionId(Command):
    def c10_connid_declare(self):
        self.parser.add_argument('--connection', '-c', type = str,
                                 help = "USB Connection ID pair in bus/device format (e.g. 001/035)")

    def c10_connid_parse(self, args):
        self.connection_id = args.connection.encode("ascii")
        
if __name__ == "__main__":
    class LolCommand:
        def __init__(self):
            pass

        def lol_declare(self):
            print("lol")

    class Test(Command, LolCommand):
        pass

    args = Test()
