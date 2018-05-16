from . import base
import click
from ..target.soc.model import SoC
from ..component.model import Cpu
from ..component.arm import dp, mem_ap
from ..component.arm.coresight import fpb
from ..util.pretty import metric
from ..util.info import TimedLogger
from ..target.memory import Loadable
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

    if erase:
        target.erase_all()
    
    if program:
        target.write(program)

    if check:
        ok = target.verify(program)
        if not ok:
            return 1

    if run:
        bus = target.bus

        fpbs = bus.children_of_class(fpb.Fpb)
        if fpbs:
            fpbs[0].disable()
        memap = bus.children_of_class(mem_ap.MemAp)
        if memap:
            memap[0].enable(False)
        dps = bus.children_of_class(dp.Dp)
        if dps:
            dps[0].debug_enable(0)

        try:
            target.reset()
        except AttributeError:
            click.echo("WARNING: Target does not handle reset")

@chip.command(help = "Readback target")
@click.argument('filename', type = str)
@click.pass_context
def readback(ctx, filename):
    target = ctx.obj["target"]

    click.echo("Target: %s" % target)

    p = Program()
    for memory in target.children_of_class(Region):
        cs = 1024

        if not isinstance(memory, (Flash, Eeprom)):
            continue

        if isinstance(memory, Flash):
            cs = memory.page_size
        
        blob = bytearray()
        for offset in range(0, memory.size, cs):
            with TimedLogger(logging, "read at %08x (%d%%)" % (offset, offset / memory.size * 100)):
                blob += memory.read(offset, cs)

        p.append(Segment(memory.address, blob))

    p.save(filename)
