from . import base
import traceback
import sys
import click
import logging

def print_va(fmt, *args):
    print(fmt % args)

def exc_pretty(e, pre = "", printer = print_va):
    m = " ".join(str(x) for x in e.args)
    if not pre:
        printer("Error: %s", m)
    else:
        printer("%sbecause of %s", pre, m)
    pre = pre + " "
    if isinstance(e, click.exceptions.BadParameter):
        p = e.param
        if isinstance(p, click.core.Option):
            printer("%sfor argument passed as %s" % (
                pre, '/'.join(p.opts)))

    elif hasattr(e, "message_get"):
        for l in e.message_get().split("\n"):
            printer(pre+l)

    else:
        for l in traceback.format_exception(type(e), e, e.__traceback__):
            printer(pre + l.rstrip())
            
        return

    cause = e.__cause__
    if cause:
        exc_pretty(cause, pre, printer)
        
def cli():
    try:
        ctx = base.cli.make_context("crobe", sys.argv[1:])
        ctx.obj = {}
        base.cli.invoke(ctx)

    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
        
    except Exception as e:
        if ctx.obj.get("raw_error", True):
            raise
        root = logging.getLogger('')
        output = print_va
        if root.level != 40:
            output = logging.getLogger('cli').critical
        exc_pretty(e, printer = output)

        try:
            ec = e.exit_code
        except:
            ec = 1
        sys.exit(ec)
