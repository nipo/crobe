from . import base
import click
import time
from ..target import pin_control

@base.cli.group(help = "Target chip manipulation")
@base.roots()
@base.field()
@click.option('--target', '-t', metavar = 'INDEX', type = int, help = 'Target index', default = 0)
@click.pass_context
def pin(ctx, roots, field, target):
    from ..target.model import Target
    targets = field.children_of_class(Target)

    ctx.obj["target"] = targets[target]

@pin.command(help = "Pin value dumper")
@click.pass_context
def dump(ctx):
    target = ctx.obj["target"]
    click.echo("Target: %s" % target)

    for name in target.pin_names:
        target.pin_config(name, pin_control.Mode.Input)
    for name in target.pin_names:
        click.echo("%s: %d" % (name, target.pin_get(name)))

@pin.command(help = "Marching test")
@click.pass_context
@click.option("--ignore", multiple = True)
def marching_test(ctx, ignore):
    target = ctx.obj["target"]
    click.echo("Target: %s" % target)

    fails = set()
    stuck = [set(), set()]
    pins = set(target.pin_names)
    pins -= set(ignore)
    pins = list(sorted(pins))

    for value in [0,1]:
        mode_in = pin_control.Mode.Input
        mode_in_value = pin_control.Mode.InputPullup if value else pin_control.Mode.InputPulldown
        mode_in_value_n = pin_control.Mode.InputPulldown if value else pin_control.Mode.InputPullup

        for name in pins:
            target.pin_config(name, mode_in)
            target.pin_set(name, value)

        for name in pins:
            before = target.pin_get_many(pins)
            target.pin_config(name, mode_in_value)
            during = target.pin_get_many(pins)
            target.pin_config(name, mode_in)
            after = target.pin_get_many(pins)

            for n in pins:
                if during[n] != before[n] and n != name:
                    print("While %s = %d, %s changed to %d" % (name, value, during[n]))
            if during[name] != value:
                print("%s set to %d, but stuck to %d" % (name, value, during[n]))
            for n in pins:
                if before[n] != after[n] and n != name:
                    print("After %s = %d, %s stuck to %d" % (name, value, n, after[n]))

@pin.command(help = "Poll inputs")
@click.pass_context
@click.option("--pullup", is_flag = True)
@click.option("--pulldown", is_flag = True)
@click.option("--ignore", multiple = True)
def poll(ctx, pullup, pulldown, ignore):
    target = ctx.obj["target"]
    click.echo("Target: %s" % target)

    mode = pin_control.Mode.Input
    if pullup:
        mode = pin_control.Mode.InputPullup
    elif pulldown:
        mode = pin_control.Mode.InputPulldown

    pins = set(target.pin_names)
    pins -= set(ignore)
    pins = list(sorted(pins))

    for name in pins:
        try:
            target.pin_config(name, mode)
        except Exception:
            print(name)
            raise

    before = target.pin_get_many(pins)

    cycles = 0
    while True:
        after = target.pin_get_many(pins)

        for n in pins:
            if after[n] != before[n]:
                print("\n%s = %d" % (n, after[n]))
                
        print("%d" % (cycles), end = "\r")
        before = after
        cycles += 1

