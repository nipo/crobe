from . import base
import sys
import click

if __name__ == "__main__":
    try:
        ctx = base.cli.make_context("crobe", sys.argv[1:])
        ctx.obj = {}
        base.cli.invoke(ctx)
    except click.exceptions.Exit as e:
        sys.exit(e.exit_code)
