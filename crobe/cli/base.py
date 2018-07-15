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

def hex_parse(ctx, param, value):
    if isinstance(value, int):
        return value
    try:
        return int(value, 16)
    except ValueError:
        raise click.BadParameter('%s should be an hex value')

def hex_parse_list(ctx, param, value):
    return [hex_parse(ctx, param, v) for v in value]

@click.group()
@click.option('-v', '--verbose', count = True)
@click.option('-q', '--quiet', count = True)
@click.option('--silent', multiple = True, type = str)
@click.pass_context
def cli(ctx, verbose, quiet, silent):
    formatter = RelativeFormatter()
    f = DomainFilter(silent)
    ctx.obj["log_filter"] = f

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(f)

    root = logging.getLogger('')
    root.addHandler(handler)
    root.setLevel(10 * (4 + quiet - verbose))
    root.info("Starting at %s", formatter.start)

def _root_parse(ctx, param, value):
    from ..adapter.model import Enumerator

    Enumerator.singleton.start()

    r = []
    for root in value:
        parts = root.split("/")
        r.append(Enumerator.singleton.child_summon(*parts))
    ctx.params["roots"] = r

def roots():
    return click.option('-r', '--root', multiple = True, type = str,
                        callback = _root_parse, expose_value = False)

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

def _program_parse(ctx, param, value):
    from ..loadable.object import Program

    ctx.params[param.name] = Program.from_files(value) if value else None

def program(name = "program"):
    return click.argument(name, nargs = -1, type = str,
                          callback = _program_parse, expose_value = False)

def program_opt(name = "program"):
    return click.option(name, multiple = True,
                        type = str,
                        callback = _program_parse,
                        expose_value = False)
