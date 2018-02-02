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
        self.parser.add_argument('--explore', '-e', type = str,
                                 action = "append",
                                 help = "Root paths to explore")

    def c10_root_parse(self, args):
        from ..adapter.model import Enumerator

        Enumerator.singleton.start()

        r = []
        for root in args.explore:
            parts = root.split("/")
            r.append(Enumerator.singleton.child_summon(*parts))
        self.roots = r

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
            except Exception:
                filename = fn
                offset = 0

            prog = Program.from_file(filename, offset)
            if len(args.programs) == 1:
                self.program = prog
                break

            self.program += prog

class Bus(Root):
    def c61_bus_declare(self):
        self.parser.add_argument('--bus', '-b', metavar = 'NAME',
                                 type = str,
                                 help = 'Bus id')

    @staticmethod
    def _bus_predicate(child, bus):
        return bus and bus in child.name.lower()

    def c61_bus_parse(self, args):
        self.bus = self.bus_get(args.bus)

    def bus_get(self, path):
        from ..component.model import Bus
        self.buses = self.roots[0].children_of_class(Bus)

        try:
            idx = int(path)
            return self.buses[idx]
        except Exception:
            pass

        try:
            t = list(filter(lambda x: self._bus_predicate(x, path.lower()), self.buses))
            return t[0]
        except AttributeError:
            pass
        except ValueError:
            pass

        for i, b in enumerate(self.buses):
            print(i, b)

        raise ValueError("Cannot find bus matching", path)

class Field(Root):
    def c60_field_parse(self, args):
        from ..target.model import Field
        from ..adapter.model import Enumerator

        self.field = Field()
        self.field.discover(Enumerator.singleton)

class Target(Field):
    expected_target = None

    def c61_target_declare(self):
        self.parser.add_argument('--target', '-t', metavar = 'NAME',
                                 type = str, default = "0",
                                 help = 'Target accessor')

    @staticmethod
    def _name_predicate(child, target):
        return target in child.name.lower()
        
    def c61_target_parse(self, args):
        from ..target.model import Field

        t = self.target_get(args.target)

        if self.expected_target is not None:
            assert isinstance(t, self.expected_target)

        self.target = t

    def target_get(self, path):
        try:
            idx = int(path)
            return self.field.children[idx]
        except Exception:
            pass

        try:
            t, = self.field.children_find(lambda x: self._name_predicate(x, path.lower()))
            return t
        except ValueError:
            pass

        raise ValueError("Cannot find target matching", path)

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
