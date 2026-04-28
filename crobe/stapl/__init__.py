"""STAPL (JESD71) parser and interpreter.

Public API:
    load(source, *, check_crc=True) -> Program
    Interpreter(program) -> interpreter
    StaplPlayer -> abstract player protocol
"""

from .lexer import tokenize, StaplError, StaplSyntaxError, StaplCrcError
from .parser import parse, Program
from .interpreter import Interpreter, StaplPlayer, StaplExit
# STAPL bit helpers re-exported under public names for transpiled output
from .interpreter import _bits_compare as bit_compare


def load(source: str, *, check_crc: bool = True) -> Program:
    """Load and parse a STAPL source file.

    Args:
        source: Full STAPL file text.
        check_crc: If True (default), verify the CRC statement.

    Returns:
        Parsed Program object ready for interpretation.
    """
    statements = tokenize(source, check_crc=check_crc)
    return parse(statements)
