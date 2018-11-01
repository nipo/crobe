from . import base
import click
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..component.arm import dp, mem_ap
from ..component.arm.coresight import fpb
from ..util.pretty import metric
from ..util.info import TimedLogger
from ..target import memory
from ..loadable.object import Program, Segment
import logging

@base.cli.group(help = "Target chip manipulation")
@base.roots()
@base.field()
@click.option('--target', '-t', metavar = 'INDEX', type = int, help = 'Target index', default = 0)
@click.pass_context
def chip(ctx, roots, field, target):
    from ..target.model import Target
    targets = field.children_of_class(Target)

    ctx.obj["target"] = targets[target]

@chip.command(help = "Program target")
@base.program()
@click.option('-e', '--erase', is_flag = True, help = "Mass erase before write")
@click.option('-c', '--check', is_flag = True, help = "Check written memory")
@click.option('--run', is_flag = True, help = "Run target after programming")
@click.pass_context
def program(ctx, program, erase, check, run):
    target = ctx.obj["target"]

    click.echo("Target: %s" % target)

    if program:
        target.write(program,
                     do_erase = erase,
                     do_verify = check,
                     do_start = run)

    else:
        if erase:
            target.erase_all()
        if run:
            try:
                target.reset()
            except AttributeError:
                click.echo("WARNING: Target does not handle reset")

@chip.command(help = "Readback target")
@click.argument('filename', type = str)
@click.pass_context
def readback(ctx, filename):
    import math

    target = ctx.obj["target"]

    click.echo("Target: %s" % target)

    target.attach()
    p = target.read()
    p.save(filename)
