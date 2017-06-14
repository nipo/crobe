import argparse
import binascii

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
        import logging
        FORMAT = '%(asctime)-15s %(name)-10s %(message)s'
        logging.basicConfig(format = FORMAT, level = 10 * (5 - args.verbose))

    def c10_adapter_declare(self):
        self.parser.add_argument('--adapter', '-a', type = str, default = "0")

    def c10_adapter_parse(self, args):
        from ..adapter.jlink import Enumerator
        self.adapter = Enumerator().get(index = int(args.adapter))
    
    def c20_interface_declare(self):
        self.parser.add_argument('--interface', '-i', type = str, default = "swd")

    def c20_interface_parse(self, args):
        self.interface = self.adapter.open(args.interface)
    
    def c24_power_declare(self):
        self.parser.add_argument('--power', '-p', action = "store_true")

    def c24_power_parse(self, args):
        import time
        self.interface.power = False
        if args.power:
            time.sleep(.3)
            self.interface.power = True
    
    def c25_icepick_declare(self):
        self.parser.add_argument('--icepick', action = "store_true")

    def c25_icepick_parse(self, args):
        self.interface.use_icepick = args.icepick

    def c30_speed_declare(self):
        self.parser.add_argument('--speed', '-s', type = int, default = 10000000)

    def c30_speed_parse(self, args):
        self.interface.speed = args.speed
        
if __name__ == "__main__":
    class LolCommand:
        def __init__(self):
            pass

        def lol_declare(self):
            print("lol")

    class Test(Command, LolCommand):
        pass

    args = Test()
