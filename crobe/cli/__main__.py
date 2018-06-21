from . import base
import sys

if __name__ == "__main__":
    ctx = base.cli.make_context("crobe", sys.argv[1:])
    ctx.obj = {}
    base.cli.invoke(ctx)
