"""STAPL (JESD71) parser.

Parses lexer output (Statement list) into a structured Program object
containing NOTE metadata, ACTION definitions, PROCEDURE blocks, and
DATA blocks with their parsed statements.
"""

from dataclasses import dataclass, field
from .lexer import Statement, StaplSyntaxError


# --- Expression AST ---

class Expr:
    """Base class for expression nodes."""
    pass


@dataclass
class IntLiteral(Expr):
    value: int


@dataclass
class VarRef(Expr):
    name: str


@dataclass
class ArrayIndex(Expr):
    name: str
    index: Expr


@dataclass
class ArraySubrange(Expr):
    name: str
    high: Expr
    low: Expr


@dataclass
class ArrayWhole(Expr):
    """Reference to an entire array: VAR[] """
    name: str


@dataclass
class UnaryOp(Expr):
    op: str  # '~', '-', '!'
    operand: Expr


@dataclass
class BinOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class FuncCall(Expr):
    name: str  # 'ABS', 'INT', 'BOOL'
    arg: Expr


# --- Boolean literal ---

class BooleanLiteral(Expr):
    """A literal Boolean array value.

    Supports lazy decoding: if _raw_text and _raw_format are set,
    the data is decoded on first access via the `data` property.
    This avoids expensive ACA decompression of multi-megabyte arrays
    at parse time.
    """
    __match_args__ = ('data', 'bit_count')

    def __init__(self, *, _data=None, bit_count, _raw_text=None, _raw_format=None):
        self._data = _data
        self.bit_count = bit_count
        self._raw_text = _raw_text
        self._raw_format = _raw_format

    @property
    def data(self) -> bytes:
        if self._data is None:
            self._data = self._decode()
            self._raw_text = None  # free the source text
        return self._data

    def _decode(self) -> bytes:
        if self._raw_format == 'aca':
            from .aca import decompress as aca_decompress
            return bytes(aca_decompress(self._raw_text))
        elif self._raw_format == 'hex':
            return bytes(_decode_hex_literal(self._raw_text))
        elif self._raw_format == 'bin':
            return bytes(_decode_binary_literal(self._raw_text))
        raise ValueError(f"Unknown raw format: {self._raw_format}")


# --- Parsed Statements ---

@dataclass
class NoteStmt:
    key: str
    value: str


@dataclass
class ActionDef:
    name: str
    description: str | None
    procedures: list[tuple[str, str | None]]  # (name, "OPTIONAL"|"RECOMMENDED"|None)


@dataclass
class ProcedureDef:
    name: str
    uses: list[str]
    statements: list  # parsed statement objects
    labels: dict[str, int]  # label_name -> statement index


@dataclass
class DataBlock:
    name: str
    statements: list  # INTEGER/BOOLEAN declarations only


# Variable declarations
@dataclass
class IntegerDecl:
    name: str
    size: Expr | None  # None = scalar, else array size
    init: list[Expr] | None  # None = zero-init


@dataclass
class BooleanDecl:
    name: str
    size: Expr | None  # None = scalar (single bit)
    init: Expr | None  # BooleanLiteral or None


# Executable statements
@dataclass
class AssignStmt:
    target: str
    index: Expr | None        # single index
    high: Expr | None         # subrange high
    low: Expr | None          # subrange low
    value: Expr


@dataclass
class GotoStmt:
    label: str


@dataclass
class CallStmt:
    procedure: str


@dataclass
class ReturnStmt:
    pass


@dataclass
class ExitStmt:
    code: Expr


@dataclass
class IfStmt:
    condition: Expr
    then_stmt: object  # a parsed statement


@dataclass
class ForStmt:
    var: str
    start: Expr
    end: Expr
    step: Expr | None


@dataclass
class NextStmt:
    var: str


@dataclass
class PushStmt:
    value: Expr


@dataclass
class PopStmt:
    target: str
    index: Expr | None


@dataclass
class LabelStmt:
    name: str


@dataclass
class DrScanStmt:
    length: Expr
    tdi: Expr
    capture: Expr | None
    compare: Expr | None
    mask: Expr | None
    result: Expr | None


@dataclass
class IrScanStmt:
    length: Expr
    tdi: Expr
    capture: Expr | None
    compare: Expr | None
    mask: Expr | None
    result: Expr | None


@dataclass
class DrStopStmt:
    state: str


@dataclass
class IrStopStmt:
    state: str


@dataclass
class StateStmt:
    path: list[str]  # list of state names, last is final


@dataclass
class WaitStmt:
    wait_state: str | None
    cycles: Expr | None
    usecs: Expr | None
    end_state: str | None
    max_cycles: Expr | None
    max_usecs: Expr | None


@dataclass
class TrstStmt:
    cycles: Expr | None
    usecs: Expr | None


@dataclass
class FrequencyStmt:
    value: Expr | None  # None = reset to default


@dataclass
class PreDrStmt:
    count: Expr
    data: Expr | None


@dataclass
class PostDrStmt:
    count: Expr
    data: Expr | None


@dataclass
class PreIrStmt:
    count: Expr
    data: Expr | None


@dataclass
class PostIrStmt:
    count: Expr
    data: Expr | None


@dataclass
class PrintStmt:
    parts: list  # list of Expr or string literals


@dataclass
class ExportStmt:
    key: str
    value: Expr


@dataclass
class VmapStmt:
    signals: list[str]


@dataclass
class VectorStmt:
    dir_vec: Expr
    in_vec: Expr
    capture: Expr | None
    compare: Expr | None
    mask: Expr | None
    result: Expr | None


# --- Program structure ---

@dataclass
class Program:
    notes: list[NoteStmt] = field(default_factory=list)
    actions: dict[str, ActionDef] = field(default_factory=dict)
    procedures: dict[str, ProcedureDef] = field(default_factory=dict)
    data_blocks: dict[str, DataBlock] = field(default_factory=dict)
    crc: int = 0


# --- Parser ---

_JTAG_STATES = frozenset({
    'RESET', 'IDLE',
    'DRSELECT', 'DRCAPTURE', 'DRSHIFT', 'DREXIT1', 'DRPAUSE', 'DREXIT2', 'DRUPDATE',
    'IRSELECT', 'IRCAPTURE', 'IRSHIFT', 'IREXIT1', 'IRPAUSE', 'IREXIT2', 'IRUPDATE',
})

_KEYWORDS = frozenset({
    'ACTION', 'BOOLEAN', 'CALL', 'CRC', 'DATA', 'DRSCAN', 'DRSTOP',
    'ENDDATA', 'ENDPROC', 'EXIT', 'EXPORT', 'FOR', 'FREQUENCY',
    'GOTO', 'IF', 'INTEGER', 'IRSCAN', 'IRSTOP', 'NEXT', 'NOTE',
    'POP', 'POSTDR', 'POSTIR', 'PREDR', 'PREIR', 'PRINT',
    'PROCEDURE', 'PUSH', 'STATE', 'TRST', 'VECTOR', 'VMAP', 'WAIT',
})


def parse(statements: list[Statement]) -> Program:
    """Parse a list of lexer statements into a Program.

    The parser processes statements in order, building up the program
    structure. Statements are organized into:
    1. NOTE statements (must come first)
    2. ACTION statements
    3. PROCEDURE and DATA blocks (interleaved)
    4. CRC statement (last)
    """
    program = Program()
    parser = _Parser(statements, program)
    parser.parse()
    return program


class _Parser:
    def __init__(self, statements: list[Statement], program: Program):
        self._stmts = statements
        self._program = program
        self._pos = 0

    def _cur(self) -> Statement | None:
        if self._pos < len(self._stmts):
            return self._stmts[self._pos]
        return None

    def _advance(self) -> Statement:
        stmt = self._stmts[self._pos]
        self._pos += 1
        return stmt

    def _keyword(self, stmt: Statement) -> str:
        """Extract the keyword from a statement."""
        text = stmt.text
        # Check for label prefix
        colon = text.find(':')
        if colon > 0:
            before = text[:colon].strip()
            if before and all(c.isalnum() or c == '_' for c in before):
                text = text[colon + 1:].strip()
                if not text:
                    return 'LABEL'

        word = text.split(None, 1)[0].upper()
        if word in _KEYWORDS:
            return word
        # Assignment: starts with variable name, contains '='
        if '=' in text:
            return 'ASSIGN'
        return word

    def _error(self, msg: str, stmt: Statement | None = None) -> StaplSyntaxError:
        line = stmt.line if stmt else None
        return StaplSyntaxError(msg, line)

    def parse(self):
        while self._cur() is not None:
            stmt = self._cur()
            kw = self._keyword(stmt)

            if kw == 'NOTE':
                self._parse_note()
            elif kw == 'ACTION':
                self._parse_action()
            elif kw == 'PROCEDURE':
                self._parse_procedure()
            elif kw == 'DATA':
                self._parse_data()
            elif kw == 'CRC':
                self._parse_crc()
            else:
                raise self._error(f"Unexpected top-level statement: {stmt.text!r}", stmt)

    def _parse_note(self):
        stmt = self._advance()
        # NOTE "key" "value"
        text = stmt.text
        _, rest = text.split(None, 1)
        parts = _split_string_args(rest)
        if len(parts) != 2:
            raise self._error(f"NOTE requires key and value strings", stmt)
        self._program.notes.append(NoteStmt(key=parts[0], value=parts[1]))

    def _parse_action(self):
        stmt = self._advance()
        # ACTION name ["description"] = proc [OPTIONAL|RECOMMENDED], ...
        text = stmt.text
        _, rest = text.split(None, 1)

        # Split on '='
        eq_pos = rest.find('=')
        if eq_pos < 0:
            raise self._error("ACTION missing '='", stmt)

        before_eq = rest[:eq_pos].strip()
        after_eq = rest[eq_pos + 1:].strip()

        # Parse name and optional description
        name, description = _parse_name_and_string(before_eq)

        # Parse procedure list
        procedures = []
        for part in _split_comma(after_eq):
            part = part.strip()
            tokens = part.split()
            proc_name = tokens[0]
            modifier = None
            if len(tokens) > 1:
                modifier = tokens[1].upper()
                assert modifier in ('OPTIONAL', 'RECOMMENDED'), \
                    f"Invalid ACTION procedure modifier: {modifier}"
            procedures.append((proc_name, modifier))

        action = ActionDef(name=name.upper(), description=description, procedures=procedures)
        self._program.actions[action.name] = action

    def _parse_procedure(self):
        stmt = self._advance()
        # PROCEDURE name [USES dep1, dep2, ...]
        text = stmt.text
        _, rest = text.split(None, 1)

        # Parse USES clause
        uses = []
        uses_pos = rest.upper().find(' USES ')
        if uses_pos >= 0:
            name = rest[:uses_pos].strip()
            uses_text = rest[uses_pos + 6:].strip()
            uses = [u.strip() for u in uses_text.split(',')]
        else:
            name = rest.strip()

        # Parse body until ENDPROC
        body_stmts = []
        labels = {}
        while self._cur() is not None:
            kw = self._keyword(self._cur())
            if kw == 'ENDPROC':
                # Record any label on the same line as ENDPROC
                # (e.g. "L84: ENDPROC" where the tokenizer merged them)
                text = self._cur().text
                colon = text.find(':')
                if colon > 0:
                    before = text[:colon].strip()
                    if before and all(c.isalnum() or c == '_' for c in before):
                        labels[before.upper()] = len(body_stmts)
                self._advance()
                break
            self._parse_body_statement_into(body_stmts, labels)
        else:
            raise self._error(f"PROCEDURE {name} missing ENDPROC", stmt)

        proc = ProcedureDef(name=name, uses=uses, statements=body_stmts, labels=labels)
        self._program.procedures[proc.name.upper()] = proc

    def _parse_data(self):
        stmt = self._advance()
        # DATA name
        _, name = stmt.text.split(None, 1)
        name = name.strip()

        body_stmts = []
        labels = {}  # unused for DATA but needed by _parse_body_statement_into
        while self._cur() is not None:
            kw = self._keyword(self._cur())
            if kw == 'ENDDATA':
                self._advance()
                break
            self._parse_body_statement_into(body_stmts, labels)
            parsed = body_stmts[-1]
            if not isinstance(parsed, (IntegerDecl, BooleanDecl)):
                raise self._error(
                    f"DATA block may only contain INTEGER/BOOLEAN declarations, got {type(parsed).__name__}",
                    self._stmts[self._pos - 1])
        else:
            raise self._error(f"DATA {name} missing ENDDATA", stmt)

        self._program.data_blocks[name.upper()] = DataBlock(name=name, statements=body_stmts)

    def _parse_crc(self):
        stmt = self._advance()
        _, val = stmt.text.split(None, 1)
        self._program.crc = int(val, 16)

    def _parse_body_statement_into(self, body: list, labels: dict):
        """Parse a statement and append to body list, recording labels."""
        stmt = self._advance()
        text = stmt.text

        # Check for label prefix
        colon = text.find(':')
        if colon > 0:
            before = text[:colon].strip()
            if before and all(c.isalnum() or c == '_' for c in before):
                labels[before.upper()] = len(body)
                text = text[colon + 1:].strip()
                if not text:
                    return  # bare label, no statement

        parsed = self._parse_statement_text(text, stmt)
        body.append(parsed)

    def _parse_statement_text(self, text: str, stmt: Statement):
        """Parse a statement from its text (label already stripped)."""
        # Extract keyword. Some generators emit "IF(" without space,
        # so we also try matching a keyword prefix.
        parts = text.split(None, 1)
        keyword = parts[0].upper()
        rest = parts[1].strip() if len(parts) > 1 else ''

        handler = getattr(self, f'_parse_{keyword.lower()}', None)
        if handler is not None:
            return handler(rest, stmt)

        # Try keyword prefix (e.g. "IF(" → keyword "IF", rest "(...")
        for kw in _KEYWORDS:
            if keyword.startswith(kw) and len(keyword) > len(kw):
                remainder = text[len(kw):].strip()
                handler = getattr(self, f'_parse_{kw.lower()}', None)
                if handler is not None:
                    return handler(remainder, stmt)

        if '=' in text:
            return self._parse_assign_text(text, stmt)

        raise self._error(f"Unknown statement: {keyword}", stmt)

    # --- Statement parsers ---
    # Each takes (rest: str, stmt: Statement) and returns a parsed statement.

    def _parse_integer(self, rest, stmt):
        return _parse_integer_decl(rest, stmt)

    def _parse_boolean(self, rest, stmt):
        return _parse_boolean_decl(rest, stmt)

    def _parse_goto(self, rest, stmt):
        return GotoStmt(label=rest.strip())

    def _parse_call(self, rest, stmt):
        return CallStmt(procedure=rest.strip())

    def _parse_endproc(self, rest, stmt):
        return ReturnStmt()

    def _parse_exit(self, rest, stmt):
        return ExitStmt(code=parse_expr(rest))

    def _parse_if(self, rest, stmt):
        # IF <expr> THEN <statement>
        then_pos = _find_keyword(rest, 'THEN')
        if then_pos < 0:
            raise StaplSyntaxError("IF missing THEN", stmt.line)
        cond_text = rest[:then_pos].strip()
        then_text = rest[then_pos + 4:].strip()
        condition = parse_expr(cond_text)
        # Parse the THEN part as a statement
        then_stmt = self._parse_inline_statement(then_text, stmt)
        return IfStmt(condition=condition, then_stmt=then_stmt)

    def _parse_inline_statement(self, text, stmt):
        """Parse an inline statement (e.g., after THEN)."""
        parts = text.split(None, 1)
        keyword = parts[0].upper()
        rest = parts[1].strip() if len(parts) > 1 else ''
        handler = getattr(self, f'_parse_{keyword.lower()}', None)
        if handler:
            return handler(rest, stmt)
        if '=' in text:
            return self._parse_assign_text(text, stmt)
        raise StaplSyntaxError(f"Unknown inline statement: {keyword}", stmt.line)

    def _parse_for(self, rest, stmt):
        # FOR var = start TO end [STEP step]
        eq_pos = rest.find('=')
        var = rest[:eq_pos].strip()

        after_eq = rest[eq_pos + 1:].strip()
        to_pos = _find_keyword(after_eq, 'TO')
        if to_pos < 0:
            raise StaplSyntaxError("FOR missing TO", stmt.line)

        start_text = after_eq[:to_pos].strip()
        after_to = after_eq[to_pos + 2:].strip()

        step_pos = _find_keyword(after_to, 'STEP')
        if step_pos >= 0:
            end_text = after_to[:step_pos].strip()
            step_text = after_to[step_pos + 4:].strip()
            step = parse_expr(step_text)
        else:
            end_text = after_to
            step = None

        return ForStmt(var=var, start=parse_expr(start_text),
                       end=parse_expr(end_text), step=step)

    def _parse_next(self, rest, stmt):
        return NextStmt(var=rest.strip())

    def _parse_push(self, rest, stmt):
        return PushStmt(value=parse_expr(rest))

    def _parse_pop(self, rest, stmt):
        # POP var or POP var[idx]
        target, index = _parse_var_ref(rest.strip())
        return PopStmt(target=target, index=index)

    def _parse_drscan(self, rest, stmt):
        return _parse_scan_stmt(rest, stmt, DrScanStmt)

    def _parse_irscan(self, rest, stmt):
        return _parse_scan_stmt(rest, stmt, IrScanStmt)

    def _parse_drstop(self, rest, stmt):
        state = rest.strip().upper()
        if not state:
            state = 'IDLE'
        return DrStopStmt(state=state)

    def _parse_irstop(self, rest, stmt):
        state = rest.strip().upper()
        if not state:
            state = 'IDLE'
        return IrStopStmt(state=state)

    def _parse_state(self, rest, stmt):
        states = rest.strip().upper().split()
        return StateStmt(path=states)

    def _parse_wait(self, rest, stmt):
        return _parse_wait_stmt(rest, stmt)

    def _parse_trst(self, rest, stmt):
        return _parse_trst_stmt(rest, stmt)

    def _parse_frequency(self, rest, stmt):
        rest = rest.strip()
        if not rest:
            return FrequencyStmt(value=None)
        return FrequencyStmt(value=parse_expr(rest))

    def _parse_predr(self, rest, stmt):
        count, data = _parse_pre_post(rest)
        return PreDrStmt(count=count, data=data)

    def _parse_postdr(self, rest, stmt):
        count, data = _parse_pre_post(rest)
        return PostDrStmt(count=count, data=data)

    def _parse_preir(self, rest, stmt):
        count, data = _parse_pre_post(rest)
        return PreIrStmt(count=count, data=data)

    def _parse_postir(self, rest, stmt):
        count, data = _parse_pre_post(rest)
        return PostIrStmt(count=count, data=data)

    def _parse_print(self, rest, stmt):
        return PrintStmt(parts=_parse_print_parts(rest))

    def _parse_export(self, rest, stmt):
        # EXPORT "key", expr
        parts = _split_comma_toplevel(rest, 2)
        if len(parts) != 2:
            raise StaplSyntaxError("EXPORT requires key and value", stmt.line)
        key = _unquote(parts[0].strip())
        value = parse_expr(parts[1].strip())
        return ExportStmt(key=key, value=value)

    def _parse_vmap(self, rest, stmt):
        parts = _split_comma_toplevel(rest)
        signals = [_unquote(p.strip()) for p in parts]
        return VmapStmt(signals=signals)

    def _parse_vector(self, rest, stmt):
        return _parse_vector_stmt(rest, stmt)

    def _parse_assign_text(self, text, stmt):
        """Parse an assignment statement from full text."""
        # Find '=' that isn't '==' or '!='
        eq_pos = _find_assignment_eq(text)
        if eq_pos < 0:
            raise StaplSyntaxError(f"Invalid assignment: {text!r}", stmt.line)

        lhs = text[:eq_pos].strip()
        rhs = text[eq_pos + 1:].strip()

        # Parse LHS: var, var[idx], var[high..low]
        target, index, high, low = _parse_lhs(lhs)
        value = parse_expr(rhs)

        return AssignStmt(target=target, index=index, high=high, low=low, value=value)


# --- Helper functions ---

def _parse_name_and_string(text: str) -> tuple[str, str | None]:
    """Parse 'NAME' or 'NAME "description"'."""
    text = text.strip()
    quote_pos = text.find('"')
    if quote_pos < 0:
        return text.strip(), None
    name = text[:quote_pos].strip()
    desc = _unquote(text[quote_pos:].strip())
    return name, desc


def _unquote(s: str) -> str:
    """Remove surrounding quotes from a string."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def _split_string_args(text: str) -> list[str]:
    """Split a text containing quoted strings into the string values."""
    result = []
    i = 0
    while i < len(text):
        if text[i] == '"':
            end = text.index('"', i + 1)
            result.append(text[i + 1:end])
            i = end + 1
        else:
            i += 1
    return result


def _split_comma(text: str) -> list[str]:
    """Split text by commas, respecting parentheses and brackets."""
    return _split_comma_toplevel(text)


def _split_comma_toplevel(text: str, max_parts: int = 0) -> list[str]:
    """Split by commas at the top level (not inside parens/brackets/strings)."""
    parts = []
    depth = 0
    current = []
    in_string = False

    for ch in text:
        if in_string:
            current.append(ch)
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            current.append(ch)
            continue
        if ch in ('(', '['):
            depth += 1
            current.append(ch)
        elif ch in (')', ']'):
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            if max_parts > 0 and len(parts) >= max_parts - 1:
                current.append(ch)
            else:
                parts.append(''.join(current))
                current = []
        else:
            current.append(ch)

    if current or parts:
        parts.append(''.join(current))

    return parts


def _find_keyword(text: str, keyword: str) -> int:
    """Find a keyword in text, not inside strings or parens. Returns offset or -1."""
    kw_upper = keyword.upper()
    kw_len = len(keyword)
    depth = 0
    in_string = False

    for i in range(len(text)):
        ch = text[i]
        if in_string:
            if ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in ('(', '['):
            depth += 1
        elif ch in (')', ']'):
            depth -= 1
        elif depth == 0:
            if text[i:i + kw_len].upper() == kw_upper:
                # Check word boundaries
                if i > 0 and (text[i - 1].isalnum() or text[i - 1] == '_'):
                    continue
                if i + kw_len < len(text) and (text[i + kw_len].isalnum() or text[i + kw_len] == '_'):
                    continue
                return i
    return -1


def _find_assignment_eq(text: str) -> int:
    """Find the '=' sign for assignment (not '==' or '!=')."""
    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch in ('(', '['):
            depth += 1
        elif ch in (')', ']'):
            depth -= 1
        elif ch == '=' and depth == 0:
            # Check it's not == or !=
            if i + 1 < len(text) and text[i + 1] == '=':
                i += 2
                continue
            if i > 0 and text[i - 1] in ('!', '<', '>'):
                i += 1
                continue
            return i
        i += 1
    return -1


def _parse_lhs(text: str) -> tuple[str, Expr | None, Expr | None, Expr | None]:
    """Parse assignment LHS: var, var[idx], var[high..low].
    Returns (name, index, high, low).
    """
    text = text.strip()
    bracket = text.find('[')
    if bracket < 0:
        return text, None, None, None

    name = text[:bracket].strip()
    inner = text[bracket + 1:text.rindex(']')].strip()

    if not inner:
        # var[] — whole array
        return name, None, None, None

    if '..' in inner:
        high_text, low_text = inner.split('..', 1)
        return name, None, parse_expr(high_text), parse_expr(low_text)

    return name, parse_expr(inner), None, None


def _parse_var_ref(text: str) -> tuple[str, Expr | None]:
    """Parse var or var[idx]."""
    bracket = text.find('[')
    if bracket < 0:
        return text, None
    name = text[:bracket].strip()
    inner = text[bracket + 1:text.rindex(']')].strip()
    return name, parse_expr(inner)


def _parse_integer_decl(rest: str, stmt: Statement) -> IntegerDecl:
    """Parse: name [= val] or name[size] [= val1, val2, ...]"""
    eq_pos = _find_assignment_eq(rest)
    if eq_pos >= 0:
        lhs = rest[:eq_pos].strip()
        rhs = rest[eq_pos + 1:].strip()
    else:
        lhs = rest.strip()
        rhs = None

    bracket = lhs.find('[')
    if bracket >= 0:
        name = lhs[:bracket].strip()
        size_text = lhs[bracket + 1:lhs.rindex(']')].strip()
        size = parse_expr(size_text)
    else:
        name = lhs
        size = None

    if rhs is not None:
        if size is not None:
            # Array init: comma-separated integer expressions
            init = [parse_expr(v.strip()) for v in _split_comma_toplevel(rhs)]
        else:
            init = [parse_expr(rhs)]
    else:
        init = None

    return IntegerDecl(name=name, size=size, init=init)


def _parse_boolean_decl(rest: str, stmt: Statement) -> BooleanDecl:
    """Parse: name [= val] or name[size] [= literal]"""
    eq_pos = _find_assignment_eq(rest)
    if eq_pos >= 0:
        lhs = rest[:eq_pos].strip()
        rhs = rest[eq_pos + 1:].strip()
    else:
        lhs = rest.strip()
        rhs = None

    bracket = lhs.find('[')
    if bracket >= 0:
        name = lhs[:bracket].strip()
        size_text = lhs[bracket + 1:lhs.rindex(']')].strip()
        size = parse_expr(size_text)
    else:
        name = lhs
        size = None

    if rhs is not None:
        init = _parse_boolean_literal_or_expr(rhs)
    else:
        init = None

    return BooleanDecl(name=name, size=size, init=init)


def _parse_boolean_literal_or_expr(text: str) -> Expr:
    """Parse a Boolean literal (#binary, $hex, @aca) or expression."""
    text = text.strip()
    if text.startswith('#'):
        return _parse_binary_literal(text[1:])
    elif text.startswith('$'):
        return _parse_hex_literal(text[1:])
    elif text.startswith('@'):
        return _parse_aca_literal(text[1:])
    else:
        return parse_expr(text)


def _decode_binary_literal(text: str) -> bytes:
    """Decode binary Boolean literal text to bytes. LSB is rightmost."""
    text = ''.join(text.split())
    bits = text[::-1]
    data = bytearray()
    for i in range(0, len(bits), 8):
        byte_bits = bits[i:i+8]
        val = 0
        for j, b in enumerate(byte_bits):
            if b == '1':
                val |= 1 << j
            elif b != '0':
                raise ValueError(f"Invalid binary digit: {b!r}")
        data.append(val)
    return bytes(data)


def _decode_hex_literal(text: str) -> bytes:
    """Decode hex Boolean literal text to bytes. LSB-first."""
    text = ''.join(text.split())
    hex_reversed = text[::-1]
    data = bytearray()
    for i in range(0, len(hex_reversed), 2):
        pair = hex_reversed[i:i+2]
        if len(pair) == 1:
            pair = pair + '0'
        val = int(pair[0], 16) | (int(pair[1], 16) << 4)
        data.append(val)
    return bytes(data)


# Threshold: literals larger than this are decoded lazily
_LAZY_THRESHOLD = 4096


def _parse_binary_literal(text: str) -> BooleanLiteral:
    """Parse binary Boolean literal (after #)."""
    clean = ''.join(text.split())
    bit_count = len(clean)
    if len(clean) > _LAZY_THRESHOLD:
        return BooleanLiteral(_data=None, bit_count=bit_count,
                              _raw_text=clean, _raw_format='bin')
    return BooleanLiteral(_data=_decode_binary_literal(clean),
                          bit_count=bit_count)


def _parse_hex_literal(text: str) -> BooleanLiteral:
    """Parse hex Boolean literal (after $)."""
    clean = ''.join(text.split())
    bit_count = len(clean) * 4
    if len(clean) > _LAZY_THRESHOLD:
        return BooleanLiteral(_data=None, bit_count=bit_count,
                              _raw_text=clean, _raw_format='hex')
    return BooleanLiteral(_data=_decode_hex_literal(clean),
                          bit_count=bit_count)


def _parse_aca_literal(text: str) -> BooleanLiteral:
    """Parse ACA-compressed Boolean literal (after @).

    Always lazy — ACA decompression is expensive (bit-by-bit
    decoding of potentially megabytes of data).
    """
    # Strip whitespace but keep the text for lazy decoding
    clean = ''.join(text.split())
    # We don't know the decompressed size without reading the header,
    # so use 0 and let the decoder set it.
    # Actually, the first 4 bytes of the decoded base64 are the length.
    # Read just enough to get the length (8 base64 chars = 6 bytes > 4 needed).
    from .aca import _text_to_bits
    header = _text_to_bits(clean[:8])
    length = int.from_bytes(header[:4], 'little')
    return BooleanLiteral(_data=None, bit_count=length * 8,
                          _raw_text=clean, _raw_format='aca')


def _parse_scan_stmt(rest: str, stmt: Statement, cls):
    """Parse DRSCAN or IRSCAN statement."""
    # DRSCAN length, tdi [, CAPTURE cap] [, COMPARE cmp, mask, result]
    parts = _split_comma_toplevel(rest)
    if len(parts) < 2:
        raise StaplSyntaxError(f"Scan statement requires at least length and data", stmt.line)

    length = parse_expr(parts[0].strip())
    tdi = parse_expr(parts[1].strip())
    capture = None
    compare = None
    mask = None
    result = None

    i = 2
    while i < len(parts):
        part = parts[i].strip()
        part_upper = part.upper()
        if part_upper.startswith('CAPTURE '):
            capture = parse_expr(part[8:].strip())
        elif part_upper.startswith('COMPARE '):
            compare = parse_expr(part[8:].strip())
            if i + 1 < len(parts):
                mask = parse_expr(parts[i + 1].strip())
                i += 1
            if i + 1 < len(parts):
                result = parse_expr(parts[i + 1].strip())
                i += 1
        else:
            raise StaplSyntaxError(f"Unexpected scan clause: {part!r}", stmt.line)
        i += 1

    return cls(length=length, tdi=tdi, capture=capture,
               compare=compare, mask=mask, result=result)


def _parse_wait_stmt(rest: str, stmt: Statement) -> WaitStmt:
    """Parse WAIT statement.

    WAIT [wait_state,] wait_type [,end_state] [MAX max_wait_type]
    wait_type: cycles CYCLES [, usecs USEC] | usecs USEC
    """
    tokens = _tokenize_wait(rest)
    wait_state = None
    cycles = None
    usecs = None
    end_state = None
    max_cycles = None
    max_usecs = None

    i = 0
    # Check for initial state name
    if i < len(tokens) and tokens[i].upper() in _JTAG_STATES:
        # Could be wait_state or end_state. If followed by comma, it's wait_state.
        if i + 1 < len(tokens) and tokens[i + 1] == ',':
            wait_state = tokens[i].upper()
            i += 2  # skip state and comma

    # Parse wait_type
    cycles, usecs, i = _parse_wait_type(tokens, i)

    # Check for comma + end_state
    if i < len(tokens) and tokens[i] == ',':
        i += 1
        if i < len(tokens) and tokens[i].upper() in _JTAG_STATES:
            end_state = tokens[i].upper()
            i += 1

    # Check for MAX
    if i < len(tokens) and tokens[i].upper() == 'MAX':
        i += 1
        max_cycles, max_usecs, i = _parse_wait_type(tokens, i)

    return WaitStmt(wait_state=wait_state, cycles=cycles, usecs=usecs,
                    end_state=end_state, max_cycles=max_cycles, max_usecs=max_usecs)


def _tokenize_wait(text: str) -> list[str]:
    """Tokenize WAIT arguments into words and commas."""
    tokens = []
    current = []
    depth = 0

    for ch in text:
        if ch in ('(', '['):
            depth += 1
            current.append(ch)
        elif ch in (')', ']'):
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            if current:
                tokens.append(''.join(current).strip())
                current = []
            tokens.append(',')
        elif ch in (' ', '\t') and depth == 0:
            if current:
                tokens.append(''.join(current).strip())
                current = []
        else:
            current.append(ch)

    if current:
        tokens.append(''.join(current).strip())

    return [t for t in tokens if t]


def _parse_wait_type(tokens: list[str], i: int) -> tuple:
    """Parse wait_type: N CYCLES [, M USEC] | N USEC."""
    cycles = None
    usecs = None

    if i >= len(tokens):
        return cycles, usecs, i

    # Try: expr CYCLES
    if i + 1 < len(tokens) and tokens[i + 1].upper() == 'CYCLES':
        cycles = parse_expr(tokens[i])
        i += 2
        # Optional: , expr USEC
        if (i + 2 < len(tokens) and tokens[i] == ','
                and tokens[i + 2].upper() == 'USEC'):
            usecs = parse_expr(tokens[i + 1])
            i += 3
    elif i + 1 < len(tokens) and tokens[i + 1].upper() == 'USEC':
        usecs = parse_expr(tokens[i])
        i += 2

    return cycles, usecs, i


def _parse_trst_stmt(rest: str, stmt: Statement) -> TrstStmt:
    """Parse TRST statement."""
    rest = rest.strip()
    if not rest:
        return TrstStmt(cycles=None, usecs=None)

    tokens = _tokenize_wait(rest)
    cycles, usecs, _ = _parse_wait_type(tokens, 0)
    return TrstStmt(cycles=cycles, usecs=usecs)


def _parse_pre_post(rest: str) -> tuple[Expr, Expr | None]:
    """Parse PRExR/POSTxR: count [, data]."""
    parts = _split_comma_toplevel(rest, 2)
    count = parse_expr(parts[0].strip())
    data = parse_expr(parts[1].strip()) if len(parts) > 1 else None
    return count, data


def _parse_print_parts(rest: str) -> list:
    """Parse PRINT arguments: mix of strings, expressions, CHR$(expr)."""
    parts = _split_comma_toplevel(rest)
    result = []
    for part in parts:
        part = part.strip()
        if part.startswith('"'):
            result.append(_unquote(part))
        else:
            result.append(parse_expr(part))
    return result


def _parse_vector_stmt(rest: str, stmt: Statement) -> VectorStmt:
    """Parse VECTOR statement."""
    parts = _split_comma_toplevel(rest)
    if len(parts) < 2:
        raise StaplSyntaxError("VECTOR requires at least dir and in vectors", stmt.line)

    dir_vec = parse_expr(parts[0].strip())
    in_vec = parse_expr(parts[1].strip())
    capture = None
    compare = None
    mask = None
    result = None

    i = 2
    while i < len(parts):
        part = parts[i].strip()
        part_upper = part.upper()
        if part_upper.startswith('CAPTURE '):
            capture = parse_expr(part[8:].strip())
        elif part_upper.startswith('COMPARE '):
            compare = parse_expr(part[8:].strip())
            if i + 1 < len(parts):
                mask = parse_expr(parts[i + 1].strip())
                i += 1
            if i + 1 < len(parts):
                result = parse_expr(parts[i + 1].strip())
                i += 1
        else:
            raise StaplSyntaxError(f"Unexpected VECTOR clause: {part!r}", stmt.line)
        i += 1

    return VectorStmt(dir_vec=dir_vec, in_vec=in_vec, capture=capture,
                      compare=compare, mask=mask, result=result)


# --- Expression Parser (Pratt / precedence climbing) ---

# Operator precedence (Table 10, JESD71): 1 = highest
_PREC = {
    '||': 1,
    '&&': 2,
    '|': 3,
    '^': 4,
    '&': 5,
    '==': 6, '!=': 6,
    '<': 7, '<=': 7, '>': 7, '>=': 7,
    '<<': 8, '>>': 8,
    '+': 9, '-': 9,
    '*': 10, '/': 10, '%': 10,
}


class _ExprParser:
    """Pratt parser for STAPL expressions."""

    def __init__(self, text: str):
        self._text = text
        self._pos = 0
        self._len = len(text)

    def _skip_ws(self):
        while self._pos < self._len and self._text[self._pos] in (' ', '\t'):
            self._pos += 1

    def _peek(self, n=1) -> str:
        return self._text[self._pos:self._pos + n]

    def _at_end(self) -> bool:
        self._skip_ws()
        return self._pos >= self._len

    def parse(self) -> Expr:
        expr = self._parse_expr(0)
        return expr

    def _parse_expr(self, min_prec: int) -> Expr:
        left = self._parse_unary()

        while True:
            self._skip_ws()
            op = self._peek_operator()
            if op is None:
                break
            prec = _PREC.get(op)
            if prec is None or prec < min_prec:
                break
            self._pos += len(op)
            right = self._parse_expr(prec + 1)
            left = BinOp(op=op, left=left, right=right)

        return left

    def _peek_operator(self) -> str | None:
        """Peek at the next binary operator."""
        if self._pos >= self._len:
            return None
        ch = self._text[self._pos]
        ch2 = self._text[self._pos:self._pos + 2]

        if ch2 in ('==', '!=', '<=', '>=', '<<', '>>', '&&', '||'):
            return ch2
        if ch in ('+', '-', '*', '/', '%', '<', '>', '&', '|', '^'):
            return ch
        return None

    def _parse_unary(self) -> Expr:
        self._skip_ws()
        if self._pos >= self._len:
            raise ValueError("Unexpected end of expression")

        ch = self._text[self._pos]

        # Unary operators
        if ch == '~':
            self._pos += 1
            operand = self._parse_unary()
            return UnaryOp(op='~', operand=operand)
        if ch == '!':
            # Check it's not !=
            if self._pos + 1 < self._len and self._text[self._pos + 1] == '=':
                pass  # not unary
            else:
                self._pos += 1
                operand = self._parse_unary()
                return UnaryOp(op='!', operand=operand)
        if ch == '-':
            # Unary minus
            self._pos += 1
            operand = self._parse_unary()
            return UnaryOp(op='-', operand=operand)

        return self._parse_primary()

    def _parse_primary(self) -> Expr:
        self._skip_ws()
        if self._pos >= self._len:
            raise ValueError("Unexpected end of expression")

        ch = self._text[self._pos]

        # Parenthesized expression
        if ch == '(':
            self._pos += 1
            expr = self._parse_expr(0)
            self._skip_ws()
            if self._pos < self._len and self._text[self._pos] == ')':
                self._pos += 1
            else:
                raise ValueError("Missing closing parenthesis")
            return expr

        # Integer literal
        if ch.isdigit():
            return self._parse_number()

        # Boolean literal
        if ch in ('#', '$', '@'):
            return self._parse_boolean_literal()

        # Identifier (variable, function, array access)
        if ch.isalpha() or ch == '_':
            return self._parse_identifier()

        raise ValueError(f"Unexpected character in expression: {ch!r}")

    def _parse_number(self) -> IntLiteral:
        start = self._pos
        while self._pos < self._len and self._text[self._pos].isdigit():
            self._pos += 1
        return IntLiteral(value=int(self._text[start:self._pos]))

    def _parse_boolean_literal(self) -> BooleanLiteral:
        ch = self._text[self._pos]
        self._pos += 1
        start = self._pos

        if ch == '#':
            while self._pos < self._len and self._text[self._pos] in ('0', '1', ' ', '\t'):
                self._pos += 1
            return _parse_binary_literal(self._text[start:self._pos])
        elif ch == '$':
            while self._pos < self._len and self._text[self._pos] in '0123456789abcdefABCDEF \t':
                self._pos += 1
            return _parse_hex_literal(self._text[start:self._pos])
        else:  # '@'
            # ACA: read until non-ACA character
            while self._pos < self._len and (self._text[self._pos].isalnum()
                                               or self._text[self._pos] in '_@'):
                self._pos += 1
            return _parse_aca_literal(self._text[start:self._pos])

    def _parse_identifier(self) -> Expr:
        start = self._pos
        while self._pos < self._len and (self._text[self._pos].isalnum() or self._text[self._pos] == '_'):
            self._pos += 1
        name = self._text[start:self._pos]
        name_upper = name.upper()

        self._skip_ws()

        # Function call: ABS(), INT(), BOOL(), CHR$()
        if name_upper in ('ABS', 'INT', 'BOOL') and self._pos < self._len and self._text[self._pos] == '(':
            self._pos += 1
            arg = self._parse_expr(0)
            self._skip_ws()
            assert self._text[self._pos] == ')', f"Missing ) after {name_upper}()"
            self._pos += 1
            return FuncCall(name=name_upper, arg=arg)

        # CHR$ function
        if name_upper == 'CHR' and self._pos < self._len and self._text[self._pos] == '$':
            self._pos += 1  # skip $
            self._skip_ws()
            assert self._text[self._pos] == '(', "Missing ( after CHR$"
            self._pos += 1
            arg = self._parse_expr(0)
            self._skip_ws()
            assert self._text[self._pos] == ')', "Missing ) after CHR$()"
            self._pos += 1
            return FuncCall(name='CHR$', arg=arg)

        # Array access
        if self._pos < self._len and self._text[self._pos] == '[':
            self._pos += 1
            self._skip_ws()
            if self._pos < self._len and self._text[self._pos] == ']':
                self._pos += 1
                return ArrayWhole(name=name)

            # Check for subrange: expr..expr
            first = self._parse_expr(0)
            self._skip_ws()
            if self._pos + 1 < self._len and self._text[self._pos:self._pos + 2] == '..':
                self._pos += 2
                second = self._parse_expr(0)
                self._skip_ws()
                assert self._text[self._pos] == ']', "Missing ] in subrange"
                self._pos += 1
                return ArraySubrange(name=name, high=first, low=second)

            assert self._text[self._pos] == ']', f"Missing ] in array index"
            self._pos += 1
            return ArrayIndex(name=name, index=first)

        return VarRef(name=name)


def parse_expr(text: str) -> Expr:
    """Parse a STAPL expression string into an AST."""
    text = text.strip()
    if not text:
        raise ValueError("Empty expression")
    parser = _ExprParser(text)
    return parser.parse()
