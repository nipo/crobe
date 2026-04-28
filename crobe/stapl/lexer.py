"""STAPL (JESD71) lexer.

Tokenizes a STAPL source file into semicolon-delimited statements.
Handles comments (apostrophe to end of line), string literals, and
CRC-16 verification.
"""

import re

from ..util.crc import Crc


class StaplError(Exception):
    def __init__(self, message, line=None):
        self.line = line
        if line is not None:
            message = f"line {line}: {message}"
        super().__init__(message)


class StaplSyntaxError(StaplError):
    pass


class StaplCrcError(StaplError):
    pass


_CRC_ALG = Crc.from_name("CRC-16/IBM-SDLC")


def _compute_crc(text: str) -> int:
    """Compute STAPL CRC-16 over file text, excluding CR characters."""
    data = text.encode("ascii").replace(b'\r', b'')
    return _CRC_ALG.calc(data)


class Statement:
    """A raw STAPL statement with its source line number."""
    __slots__ = ('line', 'text')

    def __init__(self, line: int, text: str):
        self.line = line
        self.text = text  # whitespace-normalized, no comments

    def __repr__(self):
        return f"Statement({self.line}, {self.text!r})"


# Regex to normalize whitespace outside strings.
# Splits text into string-literal and non-string segments.
_STRING_RE = re.compile(r'"[^"]*"')
_WS_RE = re.compile(r'[ \t]+')


def _normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace outside string literals to single spaces."""
    parts = []
    last_end = 0
    for m in _STRING_RE.finditer(text):
        # Process non-string segment before this match
        before = text[last_end:m.start()]
        before = _WS_RE.sub(' ', before)
        parts.append(before)
        parts.append(m.group())
        last_end = m.end()
    # Process remaining non-string text
    after = text[last_end:]
    after = _WS_RE.sub(' ', after)
    parts.append(after)
    return ''.join(parts).strip()


def tokenize(source: str, *, check_crc: bool = True) -> list[Statement]:
    """Split STAPL source into semicolon-delimited statements.

    Args:
        source: Full STAPL file text.
        check_crc: If True, verify the CRC statement.

    Returns:
        List of Statement objects. Each statement's text has comments
        stripped and whitespace normalized (but string literals preserved).

    Raises:
        StaplSyntaxError: On syntax errors.
        StaplCrcError: On CRC mismatch.
    """
    # Phase 1: strip comments, preserving strings and line structure.
    # Replace each comment ('...\n) with just \n.
    # This is safe because apostrophes cannot appear inside strings in STAPL.
    cleaned = _strip_comments(source)

    # Phase 2: split by semicolons, tracking line numbers.
    statements = []
    line_num = 1
    pos = 0

    while pos < len(cleaned):
        # Find the next semicolon or string literal
        semi = _find_semicolon(cleaned, pos)
        if semi < 0:
            # No more semicolons
            remaining = cleaned[pos:].replace('\r', '').replace('\n', ' ').strip()
            if remaining:
                raise StaplSyntaxError(f"Unterminated statement: {remaining[:60]!r}",
                                       line_num + cleaned[pos:].count('\n'))
            break

        chunk = cleaned[pos:semi]

        # Normalize: replace newlines/CR with spaces, collapse whitespace
        text = chunk.replace('\r', '').replace('\n', ' ')
        text = _normalize_whitespace(text)

        if text:
            # Find the line where the first non-whitespace of this statement begins
            stmt_line = line_num
            for ch in chunk:
                if ch == '\n':
                    stmt_line += 1
                elif ch not in (' ', '\t', '\r'):
                    break

            statements.append(Statement(stmt_line, text))

        # Count newlines in chunk for line tracking
        line_num += chunk.count('\n')
        pos = semi + 1

    if check_crc:
        _verify_crc(source, statements)

    return statements


def _strip_comments(source: str) -> str:
    """Strip comments from source, preserving string literals and newlines."""
    result = []
    i = 0
    n = len(source)

    while i < n:
        ch = source[i]

        if ch == '"':
            # String literal: copy until closing quote
            try:
                end = source.index('"', i + 1)
            except ValueError:
                line = source[:i].count('\n') + 1
                raise StaplSyntaxError("Unterminated string literal", line)
            result.append(source[i:end + 1])
            i = end + 1
            continue

        if ch == "'":
            # Comment: skip to end of line (but keep newline)
            nl = source.find('\n', i)
            if nl < 0:
                break  # comment to EOF
            i = nl  # will be picked up next iteration
            continue

        result.append(ch)
        i += 1

    return ''.join(result)


def _find_semicolon(text: str, start: int) -> int:
    """Find next semicolon not inside a string literal. Returns -1 if not found."""
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            i = text.index('"', i + 1) + 1
            continue
        if ch == ';':
            return i
        i += 1
    return -1


def _verify_crc(source: str, statements: list[Statement]) -> None:
    """Verify the CRC statement against computed CRC."""
    crc_stmt = None
    for stmt in statements:
        text_upper = stmt.text.upper()
        if text_upper.startswith('CRC ') or text_upper == 'CRC':
            crc_stmt = stmt

    if crc_stmt is None:
        raise StaplSyntaxError("Missing mandatory CRC statement")

    parts = crc_stmt.text.split(None, 1)
    if len(parts) != 2:
        raise StaplSyntaxError("CRC statement missing value", crc_stmt.line)

    declared_crc = int(parts[1], 16)
    if declared_crc == 0:
        return

    crc_pos = _find_crc_statement_pos(source)
    if crc_pos is None:
        raise StaplSyntaxError("Could not locate CRC statement in source")

    computed = _compute_crc(source[:crc_pos])
    if computed != declared_crc:
        raise StaplCrcError(
            f"CRC mismatch: declared {declared_crc:04X}, computed {computed:04X}",
            crc_stmt.line)


def _find_crc_statement_pos(source: str) -> int | None:
    """Find the character position where the last CRC statement begins."""
    i = 0
    in_string = False
    last_crc_pos = None
    n = len(source)

    while i < n:
        ch = source[i]

        if in_string:
            if ch == '"':
                in_string = False
            i += 1
            continue

        if ch == "'":
            nl = source.find('\n', i)
            if nl < 0:
                break
            i = nl + 1
            continue

        if ch == '"':
            in_string = True
            i += 1
            continue

        if (source[i:i+3].upper() == 'CRC'
            and (i == 0 or not (source[i-1].isalnum() or source[i-1] == '_'))
            and (i + 3 >= n or not (source[i+3].isalnum() or source[i+3] == '_'))):
            last_crc_pos = i

        i += 1

    return last_crc_pos
