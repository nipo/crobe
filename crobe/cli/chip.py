from . import base
import click
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..component.arm import dp, mem_ap
from ..component.arm.coresight import fpb
from ..util.pretty import metric
from ..target import memory
from ..loadable.object import Program, Segment
import logging

@base.cli.group(help = "Target chip manipulation")
@click.option('-r', '--root', "roots", type = base.ROOT, multiple = True)
@base.field()
@click.option('--target', '-t', metavar = 'CRIT', help = 'Target criterion', default = "0")
@click.pass_context
def chip(ctx, roots, field, target):
    from ..target.model import Target
    ctx.obj["target"] = field.child_summon(target)

@chip.command(help = "Program target")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.option('-C', '--assume-clean', is_flag = True, help = "Assume chip is clean")
@click.option('-e', '--erase', is_flag = True, help = "Mass erase before write")
@click.option('-c', '--check', is_flag = True, help = "Check written memory")
@click.option('--run', is_flag = True, help = "Run target after programming")
@click.option('--reset', is_flag = True, help = "Reset target after programming")
@click.option('--nodetach', is_flag = True, help = "Dont detach from target (Useful when SWO is running)")
@click.pass_context
def program(ctx, programs, assume_clean, erase, check, run, nodetach, reset):
    target = ctx.obj["target"]

    click.echo("Target: %s" % target)

    program = Program.from_programs(programs) or Program()

    program = program.simplified()
    
    target.write(program,
                 do_erase = erase,
                 do_verify = check,
                 do_start = run,
                 assume_clean = assume_clean)

    if not nodetach:
        try:
            target.detach()
        except:
            pass

    if reset:
        target.reset()
        
@chip.command(help = "Reset target")
@click.pass_context
def reset(ctx):
    target = ctx.obj["target"]
    target.attach()
    target.reset()
    target.detach()

@chip.command(help = "Check target")
@click.argument("programs", type = base.PROGRAM, nargs = -1)
@click.option('--run', is_flag = True, help = "Run target after programming")
@click.pass_context
def check(ctx, programs, run):
    target = ctx.obj["target"]

    click.echo("Target: %s" % target)

    program = Program.from_programs(programs)

    target.attach()
    
    if not target.verify(program):
        print("Verification failed")

    target.detach()

    if run:
        try:
            target.reset()
        except AttributeError:
            click.echo("WARNING: Target does not handle reset")

@chip.command(help = "Readback target")
@click.argument('filename', type = str)
@click.option('--begin', type = base.HEX, default = 0)
@click.option('--end', type = base.HEX, default = None)
@click.pass_context
def readback(ctx, filename, begin, end):
    import math

    target = ctx.obj["target"]

    click.echo("Target: %s" % target)

    target.attach()
    p = target.read(begin, end)
    p.save(filename)

@chip.command(help = "Info")
@click.pass_context
def info(ctx):
    import math

    target = ctx.obj["target"]

    click.echo("Target: %s" % target)
