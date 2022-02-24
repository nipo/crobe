import binascii
from datetime import timedelta, datetime
import logging
from .. import logger
import click
import os
from functools import update_wrapper
import re
        
@click.group()
@click.option('-v', '--verbose', count = True, help = "More verbosity")
@click.option('-e', '--raw-error', is_flag = True, help = "Do not mangle exceptions")
@click.option('-q', '--quiet', count = True, help = "Less verbosity")
@click.option('-t', '--timestamp', is_flag = True, help = "Add timestamps to log")
@click.option('-b', '--no-color', is_flag = True, help = "Dont color log")
@click.option('--silent', multiple = True, type = str, help = "Silent one component by name")
@click.option('--silent-re', type = str, help = "Silent one component by regex")
@click.option('--only-re', type = str, help = "Only components by regex", default = None)
@click.pass_context
def cli(ctx, verbose, raw_error, quiet, silent, silent_re, only_re, timestamp, no_color):
    formatter = logger.Formatter(timestamp = timestamp, color = not no_color)
    f = logger.DomainFilter(silent, silent_re, only_re)
    ctx.obj["log_filter"] = f
    ctx.obj["raw_error"] = raw_error

    base_level = "ERROR"
    base_level_int = logging._nameToLevel[base_level]
    levels = list(sorted(set(logging._levelToName.keys())))
    current = levels.index(base_level_int)
    target = min(max(0, current + quiet - verbose), len(levels)-1)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(f)

    root = logging.getLogger('')
    root.addHandler(handler)
    root.setLevel(levels[target])
    if quiet - verbose:
        root.critical("Logging level set to %s", logging.getLevelName(levels[target]))
        for level in levels:
            root.log(level, "Sample for level %s", logging._levelToName[level])
#    root.info("Starting at %s, pid %d", formatter.start, os.getpid())

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
