from . import base
import os
import sys
import click

def _path_normalize(filename):
    if filename.startswith("<") and filename.endswith(">"):
        return filename
    return os.path.normcase(os.path.abspath(filename))

def _runmodule(module_name, args):
    import runpy

    mod_name, mod_spec, code = runpy._get_module_details(module_name)
    mainpyfile = _path_normalize(code.co_filename)
    sys.argv[:] = [mainpyfile] + list(args)

    import __main__
    __main__.__dict__.clear()
    __main__.__dict__.update({
        "__name__": "__main__",
        "__file__": mainpyfile,
        "__package__": mod_spec.parent,
        "__loader__": mod_spec.loader,
        "__spec__": mod_spec,
        "__builtins__": __builtins__,
    })

    exec(code, __main__.__dict__, __main__.__dict__)

def _runscript(filename, args):
    import __main__
    __main__.__dict__.clear()
    __main__.__dict__.update({
        "__name__": "__main__",
        "__file__": filename,
        "__builtins__": __builtins__,
    })

    mainpyfile = _path_normalize(filename)
    sys.argv[:] = [mainpyfile] + list(args)

    with open(filename, "rb") as fp:
        cmd = compile(f"exec(compile({fp.read()!r}, {filename!r}, 'exec'))", "<string>", "exec")

    exec(cmd, __main__.__dict__, __main__.__dict__)

@base.cli.command(context_settings = dict(ignore_unknown_options = True),
              help = "Run module or script with initialized crobe context")
@click.option("--module", "-m", is_flag = True, help = "Run a module rather than a script")
@click.argument('entry', type = str)
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def run(module, entry, args):
    if not module and not os.path.exists(entry):
        print('Error:', entry, 'does not exist')
        sys.exit(1)

    if module:
        _runmodule(entry, args)
    else:
        sys.path[0] = os.path.dirname(entry)
        _runscript(entry, args)
    
