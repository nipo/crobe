import binascii
from datetime import timedelta, datetime
import logging
import click
from functools import update_wrapper

class RelativeFormatter(logging.Formatter):
    def __init__(self):
        logging.Formatter.__init__(self,
                                   '%(asctime)-15s %(name)-10s %(message)s',
                                   None, "%")
        self.start = datetime.now()

    def formatTime(self, record, datefmt = None):
        elapsed = datetime.now() - self.start
        return str(elapsed)

@click.group()
@click.option('-v', '--verbose', count = True)
@click.option('-q', '--quiet', count = True)
@click.pass_context
def cli(ctx, verbose, quiet):
    handler = logging.StreamHandler()
    formatter = RelativeFormatter()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(10 * (5 + quiet - verbose))
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
    return field

def _program_parse(ctx, param, value):
    from ..loadable.object import Program

    if not value:
        ctx.params["program"] = None
        return

    program = Program()

    for fn in value:
        try:
            filename, offset = fn.split("+", 1)
            offset = int(offset, 16)
            assert os.path.exists(filename)
        except Exception:
            filename = fn
            offset = 0

        prog = Program.from_file(filename, offset)
        if len(value) == 1:
            ctx.params["program"] = prog
            return

        program += prog

    ctx.params["program"] = program

def program():
    return click.argument('program', nargs = -1, type = str,
                          callback = _program_parse, expose_value = False)
