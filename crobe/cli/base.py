import binascii
from datetime import timedelta, datetime
import logging
import click
from functools import update_wrapper

class DomainFilter(logging.Filter):
    silent = set()

    def __init__(self, off):
        logging.Filter.__init__(self)
        self.silent = set(off)

    def filter(self, record):
        return record.name not in self.silent

class RelativeFormatter(logging.Formatter):
    def __init__(self):
        logging.Formatter.__init__(self,
                                   '\x1b[G\x1b[2K%(asctime)-15s %(name)-15s %(message)s',
                                   None, "%")
        self.start = datetime.now()

    def formatTime(self, record, datefmt = None):
        elapsed = datetime.now() - self.start
        return str(elapsed)

@click.group()
@click.option('-v', '--verbose', count = True, help = "More verbosity")
@click.option('-e', '--raw-error', is_flag = True, help = "Do not mangle exceptions")
@click.option('-q', '--quiet', count = True, help = "Less verbosity")
@click.option('--silent', multiple = True, type = str, help = "Silent one component by name")
@click.pass_context
def cli(ctx, verbose, raw_error, quiet, silent):
    formatter = RelativeFormatter()
    f = DomainFilter(silent)
    ctx.obj["log_filter"] = f
    ctx.obj["raw_error"] = raw_error

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(f)

    root = logging.getLogger('')
    root.addHandler(handler)
    root.setLevel(10 * (4 + quiet - verbose))
    root.info("Starting at %s", formatter.start)

##
## Custom CLI types
##

class AddressRangeParamType(click.ParamType):
    name = "address_range"

    def convert(self, value, param, ctx):
        try:
            begin, end = value.split(":", 1)
        except ValueError:
            self.fail("%r is not a valid begin:end range" % (value,), param, ctx)

        try:
            return int(begin, 16), int(end, 16)
        except ValueError:
            self.fail("%r is not a valid integer" % (value,), param, ctx)

ADDRESS_RANGE = AddressRangeParamType()

class HexParamType(click.ParamType):
    name = "hex"

    def convert(self, value, param, ctx):
        if isinstance(value, int):
            return value
        try:
            return int(value, 16)
        except ValueError:
            self.fail("%r is not a valid hex string" % (value,), param, ctx)

HEX = HexParamType()
    
class RootParamType(click.ParamType):
    name = "root"

    def convert(self, value, param, ctx):
        try:
            from ..root import root
            return root(value)
        except Exception as e:
            raise click.exceptions.BadParameter("%r is not a valid root" % (value,),
                                                param = param, ctx = ctx) from e

ROOT = RootParamType()

class ProgramParamType(click.ParamType):
    name = "program"

    def convert(self, value, param, ctx):
        from ..loadable.object import Program
        return Program.from_file(value)

PROGRAM = ProgramParamType()

def arg_adder(handler):
    name = handler.__name__

    def _arg_adder_decorator(cmd):
        @click.pass_context
        def caller(ctx, *args, **kwargs):
            kwargs[name] = handler(ctx)
            return ctx.invoke(cmd, *args, **kwargs)
        return update_wrapper(caller, cmd)

    return lambda: _arg_adder_decorator

@arg_adder
def field(ctx):
    from ..target.model import Field
    from ..adapter.model import Enumerator

    field = Field()
    for r in ctx.params["roots"]:
        field.discover(r)
    for t in field.children:
        t.start()
    return field
