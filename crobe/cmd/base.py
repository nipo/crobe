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
        self.parser.add_argument('--verbose', '-v', action='count', default = 0)

    def c00_verbose_parse(self, args):
        handler = logging.StreamHandler()
        formatter = RelativeFormatter()
        handler.setFormatter(formatter)
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(10 * (5 - args.verbose))

        root.info("Starting at %s", formatter.start)

class Adapter(Command):
    def c10_adapter_declare(self):
        self.parser.add_argument('--adapter', '-a', type = str, default = "0")

    def c10_adapter_parse(self, args):
        from ..adapter.model import Enumerator, Adapter

        Enumerator.singleton.start()

        adapters = Enumerator.singleton.children_find(lambda x: True)

        try:
            index = int(args.adapter)
            self.adapter = adapters[index]
            return
        except ValueError as e:
            pass

        adapters = [a for a in adapters if a.name.lower() == args.adapter.lower()]
        if len(adapters) == 1:
            self.adapter = adapters[0]
            return

        raise ValueError("Adapter not found", args.adapter)
    
class Interface(Adapter):
    def c20_interface_declare(self):
        self.parser.add_argument('--interface', '-i', type = str, default = "swd")

    def c20_interface_parse(self, args):
        self.interface = self.adapter.open(args.interface)

class Speed(Interface):
    def c30_speed_declare(self):
        self.parser.add_argument('--speed', '-s', type = int, default = 10000000)

    def c30_speed_parse(self, args):
        self.interface.speed = args.speed
    
class Power(Interface):
    def c24_power_declare(self):
        self.parser.add_argument('--power', '-p', type = str, default = "")

    def c24_power_parse(self, args):
        import time
        if args.power:
            self.interface.power = args.power.lower() in ["on", "1", "true"]
            time.sleep(.05)
    
class IcePick(Interface):
    def c25_icepick_declare(self):
        self.parser.add_argument('--icepick', action = "store_true")

    def c25_icepick_parse(self, args):
        self.interface.use_icepick = args.icepick
        
if __name__ == "__main__":
    class LolCommand:
        def __init__(self):
            pass

        def lol_declare(self):
            print("lol")

    class Test(Command, LolCommand):
        pass

    args = Test()
