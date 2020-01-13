from . import base
import click
import os
import os.path

def repl_config(repl):
    repl.show_signature = True
    repl.show_docstring = True
    repl.highlight_matching_parenthesis = True
    repl.wrap_lines = True
    repl.prompt_style = 'classic'
    repl.confirm_exit = False
    repl.color_depth = 'DEPTH_24_BIT'
    repl.enable_syntax_highlighting = True

@base.cli.command(help = "Interactive CLI")
def repl():
    from .. import root
    from .. import bitstring

    from ptpython.repl import embed

    try:
        os.makedirs(os.path.expanduser('~/.local/crobe/'))
    except:
        pass
    
    embed(
        globals(),
        dict(root = root.root, BitString = bitstring.BitString),
        configure = repl_config,
        title = "Crobe",
        history_filename = os.path.expanduser('~/.local/crobe/repl.history'),
    )
