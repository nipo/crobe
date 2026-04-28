"""STAPL to Python transpiler.

Converts a parsed STAPL program into a standalone Python script that
executes the same JTAG operations using crobe's synchronous JTAG
Interface API.

The output separates code (procedures) from data (large boolean literals),
externalizing big arrays as binary files and emitting readable Python
with recovered control flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .parser import (
    Program, ActionDef, ProcedureDef, DataBlock,
    IntegerDecl, BooleanDecl, BooleanLiteral,
    AssignStmt, GotoStmt, CallStmt, ExitStmt, IfStmt,
    ForStmt, NextStmt, PushStmt, PopStmt, ReturnStmt,
    DrScanStmt, IrScanStmt, DrStopStmt, IrStopStmt,
    StateStmt, WaitStmt, TrstStmt, FrequencyStmt,
    PreDrStmt, PostDrStmt, PreIrStmt, PostIrStmt,
    PrintStmt, ExportStmt, VmapStmt, VectorStmt,
    Expr, IntLiteral, VarRef, ArrayIndex, ArraySubrange,
    ArrayWhole, UnaryOp, BinOp, FuncCall,
)


# ============================================================
# Helpers
# ============================================================

def _try_const_fold(expr: Expr, constants: dict[str, int] | None = None) -> int | None:
    """Try to constant-fold an expression to an integer. Returns None if not constant.

    If constants is provided, variable references to known constants
    are resolved.
    """
    match expr:
        case IntLiteral(value=v):
            return v
        case VarRef(name=n) if constants is not None and n in constants:
            return constants[n]
        case UnaryOp(op='-', operand=inner):
            v = _try_const_fold(inner, constants)
            return -v if v is not None else None
        case UnaryOp(op='~', operand=inner):
            v = _try_const_fold(inner, constants)
            return ~v if v is not None else None
        case UnaryOp(op='!', operand=inner):
            v = _try_const_fold(inner, constants)
            return int(not v) if v is not None else None
        case BinOp(op=op, left=l, right=r):
            lv = _try_const_fold(l, constants)
            rv = _try_const_fold(r, constants)
            if lv is None or rv is None:
                return None
            match op:
                case '+': return lv + rv
                case '-': return lv - rv
                case '*': return lv * rv
                case '/': return lv // rv if rv else None
                case '%': return lv % rv if rv else None
                case '&': return lv & rv
                case '|': return lv | rv
                case '^': return lv ^ rv
                case '==': return int(lv == rv)
                case '!=': return int(lv != rv)
                case '>': return int(lv > rv)
                case '<': return int(lv < rv)
                case '>=': return int(lv >= rv)
                case '<=': return int(lv <= rv)
                case '&&': return int(bool(lv) and bool(rv))
                case '||': return int(bool(lv) or bool(rv))
                case '<<': return lv << rv
                case '>>': return lv >> rv
                case _: return None
        case _:
            return None


# ============================================================
# Configuration
# ============================================================

@dataclass
class EnumDef:
    """An integer enum type for the transpiled output."""
    class_name: str
    values: dict[int, str]  # numeric value → symbolic name
    variables: set[str]  # variable names tagged with this enum

@dataclass
class BitfieldDef:
    """A bitfield (IntFlag) type for the transpiled output."""
    class_name: str
    values: dict[int, str]  # bit mask → symbolic name
    variables: set[str]  # variable names tagged with this bitfield


@dataclass
class TranspileConfig:
    data_threshold: int = 256  # bits; boolean arrays >= this → binary files
    rename_map: dict[str, str] | None = None  # original name → new name
    enums: list[EnumDef] = field(default_factory=list)
    bitfields: list[BitfieldDef] = field(default_factory=list)

    def rename(self, name: str) -> str:
        """Apply rename map to a name."""
        if self.rename_map is not None and name in self.rename_map:
            return self.rename_map[name]
        return name

    @staticmethod
    def from_yaml(path: str) -> 'TranspileConfig':
        """Load config from a YAML file."""
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f) or {}

        rename_map = None
        raw_rename = data.get('rename', {})
        if raw_rename:
            rename_map = {}
            for key, val in raw_rename.items():
                k = str(key)
                # Accept _proc_xxx as convenience for procedure XXX
                if k.startswith('_proc_'):
                    k = k[6:].upper()
                rename_map[k] = str(val)

        enums = []
        for name, edef in data.get('enums', {}).items():
            values = {int(k): str(v) for k, v in edef.get('values', {}).items()}
            variables = {str(v) for v in edef.get('variables', [])}
            enums.append(EnumDef(class_name=name, values=values,
                                 variables=variables))

        bitfields = []
        for name, bdef in data.get('bitfields', {}).items():
            values = {int(k): str(v) for k, v in bdef.get('values', {}).items()}
            variables = {str(v) for v in bdef.get('variables', [])}
            bitfields.append(BitfieldDef(class_name=name, values=values,
                                         variables=variables))

        return TranspileConfig(
            data_threshold=data.get('data_threshold', 256),
            rename_map=rename_map,
            enums=enums,
            bitfields=bitfields,
        )


def _apply_rename_map(program: Program, rename: dict[str, str]) -> Program:
    """Apply a rename map to all identifiers in a parsed Program.

    Returns a new Program with renamed variables, procedures, data blocks,
    and labels. The original program is not modified.
    """
    import copy
    prog = copy.deepcopy(program)
    r = rename.get

    def _rename_expr(expr):
        if expr is None:
            return
        match expr:
            case VarRef():
                expr.name = r(expr.name, expr.name)
            case ArrayIndex():
                expr.name = r(expr.name, expr.name)
                _rename_expr(expr.index)
            case ArraySubrange():
                expr.name = r(expr.name, expr.name)
                _rename_expr(expr.high)
                _rename_expr(expr.low)
            case ArrayWhole():
                expr.name = r(expr.name, expr.name)
            case BinOp():
                _rename_expr(expr.left)
                _rename_expr(expr.right)
            case UnaryOp():
                _rename_expr(expr.operand)
            case FuncCall():
                _rename_expr(expr.arg)

    def _rename_stmt(stmt):
        match stmt:
            case IntegerDecl():
                stmt.name = r(stmt.name, stmt.name)
                _rename_expr(stmt.size)
                if stmt.init:
                    for e in stmt.init:
                        _rename_expr(e)
            case BooleanDecl():
                stmt.name = r(stmt.name, stmt.name)
                _rename_expr(stmt.size)
                if stmt.init and not isinstance(stmt.init, BooleanLiteral):
                    _rename_expr(stmt.init)
            case AssignStmt():
                stmt.target = r(stmt.target, stmt.target)
                _rename_expr(stmt.index)
                _rename_expr(stmt.high)
                _rename_expr(stmt.low)
                _rename_expr(stmt.value)
            case IfStmt():
                _rename_expr(stmt.condition)
                _rename_stmt(stmt.then_stmt)
            case ForStmt():
                stmt.var = r(stmt.var, stmt.var)
                _rename_expr(stmt.start)
                _rename_expr(stmt.end)
                if stmt.step:
                    _rename_expr(stmt.step)
            case NextStmt():
                stmt.var = r(stmt.var, stmt.var)
            case GotoStmt():
                stmt.label = r(stmt.label, stmt.label)
            case CallStmt():
                stmt.procedure = r(stmt.procedure, stmt.procedure)
            case ExitStmt():
                _rename_expr(stmt.code)
            case PushStmt():
                _rename_expr(stmt.value)
            case PopStmt():
                stmt.target = r(stmt.target, stmt.target)
                _rename_expr(stmt.index)
            case PrintStmt():
                for i, p in enumerate(stmt.parts):
                    if not isinstance(p, str):
                        _rename_expr(p)
            case ExportStmt():
                _rename_expr(stmt.value)
            case DrScanStmt() | IrScanStmt():
                _rename_expr(stmt.length)
                _rename_expr(stmt.tdi)
                _rename_expr(stmt.capture)
                _rename_expr(stmt.compare)
                _rename_expr(stmt.mask)
                _rename_expr(stmt.result)
            case PreDrStmt() | PostDrStmt() | PreIrStmt() | PostIrStmt():
                _rename_expr(stmt.count)
                _rename_expr(stmt.data)
            case WaitStmt():
                _rename_expr(stmt.cycles)
                _rename_expr(stmt.usecs)
            case FrequencyStmt():
                _rename_expr(stmt.value)

    # Rename procedures
    new_procs = {}
    for name, proc in prog.procedures.items():
        new_name = r(name, name)
        proc.name = new_name
        proc.uses = [r(u.upper(), u.upper()) for u in proc.uses]
        # Rename labels
        proc.labels = {r(lbl, lbl): idx for lbl, idx in proc.labels.items()}
        for stmt in proc.statements:
            _rename_stmt(stmt)
        new_procs[new_name] = proc
    prog.procedures = new_procs

    # Rename data blocks
    new_data = {}
    for name, db in prog.data_blocks.items():
        new_name = r(name, name)
        db.name = new_name
        for stmt in db.statements:
            _rename_stmt(stmt)
        new_data[new_name] = db
    prog.data_blocks = new_data

    # Rename actions
    new_actions = {}
    for name, action in prog.actions.items():
        new_name = r(name, name)
        action.name = new_name
        action.procedures = [(r(p, p), mod) for p, mod in action.procedures]
        new_actions[new_name] = action
    prog.actions = new_actions

    return prog


# ============================================================
# Variable information
# ============================================================

@dataclass
class VarInfo:
    name: str
    vtype: str  # 'integer' | 'boolean'
    is_array: bool
    size: int | None  # bit count for boolean, element count for integer
    has_init: bool
    init_data: bytes | None  # raw bytes for boolean with literal init
    init_bit_count: int | None
    scope: str  # 'data' | 'local'
    data_block: str | None  # DATA block name, if scope == 'data'
    is_read: bool = True  # False if variable is never read (dead)
    is_const: bool = False  # True if scalar int, has init, never reassigned
    const_value: int | None = None
    extern_filename: str | None = None  # .bin filename if externalized


# ============================================================
# FOR/NEXT region extraction
# ============================================================

@dataclass
class ForRegion:
    """A FOR/NEXT structured region extracted from flat statement list."""
    for_stmt: ForStmt
    body: list  # may contain nested ForRegions and other stmts
    next_stmt: NextStmt


def _find_matching_next(stmts, for_idx):
    """Find the matching NEXT for a FOR at for_idx (by nesting depth)."""
    depth = 1
    for j in range(for_idx + 1, len(stmts)):
        if isinstance(stmts[j], ForStmt):
            depth += 1
        elif isinstance(stmts[j], NextStmt):
            depth -= 1
            if depth == 0:
                return j
    assert False, f"No matching NEXT for FOR at index {for_idx}"


def _extract_for_regions(stmts):
    """Replace FOR/NEXT pairs with ForRegion nodes. Returns processed list."""
    result = []
    i = 0
    while i < len(stmts):
        if isinstance(stmts[i], ForStmt):
            end = _find_matching_next(stmts, i)
            body = _extract_for_regions(stmts[i + 1:end])
            result.append(ForRegion(stmts[i], body, stmts[end]))
            i = end + 1
        else:
            result.append(stmts[i])
            i += 1
    return result


def _preprocess_for_next(stmts, labels):
    """Extract FOR/NEXT regions and adjust label indices.

    Returns (processed_stmts, adjusted_labels).
    FOR/NEXT pairs that contain labels are left as raw statements
    (the dispatch will handle them). Inner FOR/NEXT pairs that don't
    contain labels are still extracted even if their outer FOR does.
    """
    # Find ALL FOR/NEXT pairs at every nesting level using a stack
    all_pairs = {}  # for_idx → next_idx
    stack = []
    for i, stmt in enumerate(stmts):
        if isinstance(stmt, ForStmt):
            stack.append(i)
        elif isinstance(stmt, NextStmt):
            if stack:
                for_idx = stack.pop()
                all_pairs[for_idx] = i

    # Remove pairs that DIRECTLY contain labels
    # (a label at index L is "inside" FOR[f]..NEXT[n] if f < L <= n)
    label_indices = set(labels.values())
    tainted = set()
    for f_start, f_end in all_pairs.items():
        for idx in label_indices:
            if f_start < idx <= f_end:
                tainted.add(f_start)
                break
    for t in tainted:
        del all_pairs[t]

    # Only keep outermost non-tainted pairs for top-level extraction.
    # Inner pairs will be extracted recursively by _extract_for_regions.
    outermost = {}
    sorted_pairs = sorted(all_pairs.items())
    skip_until = -1
    for f_start, f_end in sorted_pairs:
        if f_start > skip_until:
            outermost[f_start] = f_end
            skip_until = f_end

    # Build processed list with old→new index mapping
    processed = []
    old_to_new = {}
    i = 0
    while i < len(stmts):
        old_to_new[i] = len(processed)
        if i in outermost:
            next_idx = outermost[i]
            body = _extract_for_regions(stmts[i + 1:next_idx])
            processed.append(ForRegion(stmts[i], body, stmts[next_idx]))
            for j in range(i + 1, next_idx + 1):
                old_to_new[j] = len(processed) - 1
            i = next_idx + 1
        else:
            processed.append(stmts[i])
            i += 1

    # Also map index == len(stmts) for labels pointing past end
    old_to_new[len(stmts)] = len(processed)

    adjusted = {}
    for label, idx in labels.items():
        adjusted[label] = old_to_new[idx]

    return processed, adjusted


# ============================================================
# Basic block construction
# ============================================================

@dataclass
class Fallthrough:
    pass


@dataclass
class Jump:
    target: str


@dataclass
class CondJump:
    condition: Expr
    target: str  # taken when condition is true


@dataclass
class BlockExit:
    code: Expr


@dataclass
class BlockReturn:
    pass


@dataclass
class Block:
    name: str
    index: int  # position in source order
    stmts: list  # non-terminal statements (may include ForRegion)
    terminal: Fallthrough | Jump | CondJump | BlockExit | BlockReturn


def _build_blocks(stmts, labels):
    """Build basic blocks from preprocessed statement list.

    Args:
        stmts: list of statements and ForRegions (FOR/NEXT already extracted)
        labels: dict[str, int] adjusted label → index mapping

    Returns:
        (blocks, name_to_idx) where blocks is a list of Block and
        name_to_idx maps block names to list indices.
    """
    # Reverse label map: index → label name (first label wins)
    idx_to_label = {}
    for label, idx in labels.items():
        if idx not in idx_to_label:
            idx_to_label[idx] = label

    # Find all block boundary indices
    boundaries = {0}
    for _, idx in labels.items():
        boundaries.add(idx)

    for i, stmt in enumerate(stmts):
        if isinstance(stmt, GotoStmt):
            boundaries.add(i + 1)
            target = stmt.label
            target = (target)
            if target in labels:
                boundaries.add(labels[target])
        elif isinstance(stmt, IfStmt) and isinstance(stmt.then_stmt, GotoStmt):
            boundaries.add(i + 1)
            target = stmt.then_stmt.label
            if target in labels:
                boundaries.add(labels[target])
        elif isinstance(stmt, ExitStmt):
            boundaries.add(i + 1)

    # Sort and filter valid boundaries
    boundaries = sorted(b for b in boundaries if 0 <= b <= len(stmts))
    if not boundaries or boundaries[0] != 0:
        boundaries = [0] + boundaries

    # Create blocks
    blocks = []
    for bi in range(len(boundaries)):
        start = boundaries[bi]
        end = boundaries[bi + 1] if bi + 1 < len(boundaries) else len(stmts)

        if start >= len(stmts):
            # Label at the very end of the procedure (e.g. before ENDPROC).
            # Still create an empty block so GOTOs to it work.
            name = idx_to_label.get(start, f'_block_{start}')
            blocks.append(Block(name, bi, [], Fallthrough()))
            break

        name = idx_to_label.get(start, f'_block_{start}')
        block_stmts = []
        terminal = Fallthrough()

        for j in range(start, end):
            s = stmts[j]

            if isinstance(s, GotoStmt):
                terminal = Jump(s.label)
                break
            elif isinstance(s, IfStmt) and isinstance(s.then_stmt, GotoStmt):
                terminal = CondJump(s.condition, s.then_stmt.label)
                break
            elif isinstance(s, ExitStmt):
                terminal = BlockExit(s.code)
                break
            else:
                block_stmts.append(s)

        blocks.append(Block(name, bi, block_stmts, terminal))

    # Append implicit return if last block falls through
    if blocks and isinstance(blocks[-1].terminal, Fallthrough):
        blocks[-1].terminal = BlockReturn()

    name_to_idx = {b.name: i for i, b in enumerate(blocks)}
    return blocks, name_to_idx


# ============================================================
# Control flow recovery
# ============================================================

# Structured IR nodes

@dataclass
class SStmt:
    """A plain statement (or ForRegion)."""
    stmt: object


@dataclass
class SFor:
    """Python for loop."""
    var: str
    start: Expr
    end: Expr
    step: Expr | None
    body: list  # of structured nodes


@dataclass
class SWhileTrue:
    """while True loop with breaks inside."""
    body: list


@dataclass
class SWhile:
    """while condition loop."""
    condition: Expr
    body: list


@dataclass
class SIf:
    """if/elif/else."""
    condition: Expr
    then_body: list
    else_body: list | None


@dataclass
class SBreak:
    pass


@dataclass
class SContinue:
    pass


@dataclass
class SExit:
    code: Expr


@dataclass
class SReturn:
    pass


@dataclass
class SDispatch:
    """Fallback: block dispatch for unrecoverable control flow."""
    entry: str
    blocks: list[Block]
    name_to_idx: dict[str, int]


def _negate_expr(expr: Expr) -> Expr:
    """Negate an expression. Simplify double negation and comparisons."""
    if isinstance(expr, UnaryOp) and expr.op == '!':
        return expr.operand
    _flip = {'==': '!=', '!=': '==', '<': '>=', '>': '<=', '<=': '>', '>=': '<'}
    if isinstance(expr, BinOp) and expr.op in _flip:
        return BinOp(_flip[expr.op], expr.left, expr.right)
    return UnaryOp('!', expr)


def _has_unresolved_gotos(nodes):
    """Check if any structured IR nodes contain unresolved GotoStmt.

    Also checks for SBreak/SContinue inside nested loops where they
    might not exit to the right level (the structured recovery may
    have mapped a GOTO-to-procedure-exit as a simple break, but if
    the break is inside nested while loops, it only exits the
    innermost one).
    """
    return _check_gotos(nodes, loop_depth=0)


def _check_gotos(nodes, loop_depth):
    for node in nodes:
        match node:
            case SWhileTrue(body=body):
                if _check_gotos(body, loop_depth + 1):
                    return True
            case SWhile(body=body):
                if _check_gotos(body, loop_depth + 1):
                    return True
            case SIf(then_body=body, else_body=eb):
                if _check_gotos(body, loop_depth):
                    return True
                if eb and _check_gotos(eb, loop_depth):
                    return True
            case SFor(body=body):
                if _check_gotos(body, loop_depth + 1):
                    return True
            case SStmt(stmt=s):
                if isinstance(s, GotoStmt):
                    return True
                if isinstance(s, IfStmt) and isinstance(s.then_stmt, GotoStmt):
                    return True
            case SBreak():
                # A break inside depth > 1 means it was a GOTO that
                # crossed a loop boundary — the break only exits the
                # innermost loop, not the target scope.
                if loop_depth > 1:
                    return True
    return False


def _recover_control_flow(blocks, name_to_idx):
    """Attempt to recover structured control flow from basic blocks.

    Returns a list of structured IR nodes. Falls back to SDispatch
    if the control flow cannot be fully recovered, or if unresolved
    GOTO statements remain after structuring.
    """
    if not blocks:
        return []

    try:
        result = _structure_region(blocks, 0, len(blocks), name_to_idx)
        # Check for leftover GOTOs that the structurer couldn't handle
        if _has_unresolved_gotos(result):
            return [SDispatch(blocks[0].name, blocks, name_to_idx)]
        return result
    except _UnstructurableError:
        return [SDispatch(blocks[0].name, blocks, name_to_idx)]


class _UnstructurableError(Exception):
    pass


def _structure_region(blocks, start, end, name_to_idx):
    """Recursively structure blocks[start:end] into structured IR.

    Raises _UnstructurableError if a goto target falls outside the
    region or can't be matched to a known pattern.
    """
    if start >= end:
        return []

    # Find back-edges (loops) within this region
    # back-edge: block i has a jump to block j where j >= start and j <= i
    loops = {}  # header_block_idx → tail_block_idx
    for i in range(start, end):
        block = blocks[i]
        targets = _get_jump_targets(block, name_to_idx)
        for t in targets:
            if start <= t <= i:
                # Back-edge from block i to block t
                if t not in loops or i > loops[t]:
                    loops[t] = i

    result = []
    i = start
    while i < end:
        # Check if we're at a loop header
        if i in loops:
            tail = loops[i]
            loop_node = _structure_loop(blocks, i, tail, name_to_idx)
            result.append(loop_node)
            i = tail + 1
            continue

        block = blocks[i]

        # Emit block's non-terminal statements
        for stmt in block.stmts:
            result.append(_wrap_stmt(stmt))

        # Handle terminal
        if isinstance(block.terminal, CondJump):
            target_idx = name_to_idx.get(block.terminal.target)
            if target_idx is None or target_idx < start or target_idx > end:
                raise _UnstructurableError(
                    f"CondJump target {block.terminal.target} out of region [{start}:{end}]")

            if target_idx <= i:
                # Back-edge handled above, shouldn't reach here
                raise _UnstructurableError("Unexpected back-edge in linear scan")

            # Forward conditional jump: if/else pattern
            if_node = _try_structure_if(blocks, i, target_idx, end, name_to_idx)
            if if_node is not None:
                result.append(if_node[0])
                i = if_node[1]
                continue
            else:
                raise _UnstructurableError(
                    f"Cannot structure forward jump from block {i} to {target_idx}")

        elif isinstance(block.terminal, Jump):
            target_idx = name_to_idx.get(block.terminal.target)
            if target_idx is None:
                raise _UnstructurableError(
                    f"Jump target {block.terminal.target} not found")
            if target_idx == i + 1:
                pass  # redundant goto to next block, ignore
            elif target_idx > i:
                # Forward unconditional jump — could be part of if/else (skip else)
                # or a break. Hard to handle in isolation.
                raise _UnstructurableError(
                    f"Standalone forward jump from block {i} to {target_idx}")
            else:
                # Back-edge: should have been caught as loop
                raise _UnstructurableError(
                    f"Standalone back-jump from block {i} to {target_idx}")

        elif isinstance(block.terminal, BlockExit):
            result.append(SExit(block.terminal.code))

        elif isinstance(block.terminal, BlockReturn):
            # Only emit explicit return if it's not the last block
            if i < end - 1:
                result.append(SReturn())

        i += 1

    return result


def _structure_loop(blocks, header_idx, tail_idx, name_to_idx):
    """Structure a loop from blocks[header_idx] through blocks[tail_idx].

    The back-edge is at blocks[tail_idx] jumping back to blocks[header_idx].
    """
    header = blocks[header_idx]
    tail = blocks[tail_idx]

    # Determine loop type based on where the condition is

    # Case 1: Condition at tail (bottom-tested loop)
    # while True: body; if not cond: break
    if isinstance(tail.terminal, CondJump):
        target_idx = name_to_idx.get(tail.terminal.target)
        if target_idx == header_idx:
            # Back-edge is the conditional: loop back if condition true
            # → while True: body; if not cond: break
            body = _structure_loop_body(blocks, header_idx, tail_idx, name_to_idx)
            # Add tail's statements
            for stmt in tail.stmts:
                body.append(_wrap_stmt(stmt))
            # Add break condition (loop continues if condition true, break if false)
            body.append(SIf(_negate_expr(tail.terminal.condition), [SBreak()], None))
            return SWhileTrue(body)

    # Case 2: Condition at header (top-tested loop)
    if isinstance(header.terminal, CondJump):
        exit_target = name_to_idx.get(header.terminal.target)
        if exit_target is not None and exit_target == tail_idx + 1:
            # Header jumps past the loop when condition is true → while not cond
            if not header.stmts:
                # Clean while loop: no statements before condition
                body = _structure_loop_body(
                    blocks, header_idx + 1, tail_idx, name_to_idx)
                # Add tail's statements to body
                for stmt in blocks[tail_idx].stmts:
                    body.append(_wrap_stmt(stmt))
                return SWhile(_negate_expr(header.terminal.condition), body)
            else:
                # Header has statements before the condition
                body = []
                for stmt in header.stmts:
                    body.append(_wrap_stmt(stmt))
                body.append(SIf(header.terminal.condition, [SBreak()], None))
                body.extend(
                    _structure_loop_body(
                        blocks, header_idx + 1, tail_idx, name_to_idx))
                for stmt in blocks[tail_idx].stmts:
                    body.append(_wrap_stmt(stmt))
                return SWhileTrue(body)

    # Case 3: Unconditional back-edge at tail (while True, break inside)
    if isinstance(tail.terminal, Jump):
        target_idx = name_to_idx.get(tail.terminal.target)
        if target_idx == header_idx:
            body = _structure_loop_body(blocks, header_idx, tail_idx, name_to_idx)
            for stmt in tail.stmts:
                body.append(_wrap_stmt(stmt))
            return SWhileTrue(body)

    # Fallback: while True with entire range as body
    body = []
    for bi in range(header_idx, tail_idx + 1):
        for stmt in blocks[bi].stmts:
            body.append(_wrap_stmt(stmt))
        t = blocks[bi].terminal
        if isinstance(t, CondJump):
            target_idx = name_to_idx.get(t.target)
            if target_idx == header_idx:
                body.append(SIf(_negate_expr(t.condition), [SBreak()], None))
            elif target_idx is not None and target_idx > tail_idx:
                body.append(SIf(t.condition, [SBreak()], None))
        elif isinstance(t, BlockExit):
            body.append(SExit(t.code))
    return SWhileTrue(body)


def _structure_loop_body(blocks, start, end, name_to_idx):
    """Structure the interior of a loop (blocks[start:end], exclusive of tail)."""
    if start >= end:
        return []
    try:
        return _structure_region(blocks, start, end, name_to_idx)
    except _UnstructurableError:
        # Fall back to emitting statements linearly
        body = []
        for bi in range(start, end):
            for stmt in blocks[bi].stmts:
                body.append(_wrap_stmt(stmt))
            t = blocks[bi].terminal
            if isinstance(t, CondJump):
                # Emit as if-break or if-continue
                target_idx = name_to_idx.get(t.target)
                if target_idx is not None and target_idx > end:
                    body.append(SIf(t.condition, [SBreak()], None))
                elif target_idx is not None and target_idx == start:
                    body.append(SIf(t.condition, [SContinue()], None))
                else:
                    body.append(SIf(t.condition,
                                    [SStmt(GotoStmt(t.target))], None))
            elif isinstance(t, Jump):
                target_idx = name_to_idx.get(t.target)
                if target_idx is not None and target_idx > end:
                    body.append(SBreak())
                elif target_idx == start:
                    body.append(SContinue())
            elif isinstance(t, BlockExit):
                body.append(SExit(t.code))
        return body


def _try_structure_if(blocks, cond_block_idx, target_idx, region_end, name_to_idx):
    """Try to structure an if/else pattern.

    cond_block_idx: block with the conditional forward jump
    target_idx: where the jump goes (else branch start or merge point)

    Returns (structured_node, next_idx) or None if pattern doesn't match.
    """
    cond_block = blocks[cond_block_idx]
    condition = cond_block.terminal.condition

    # Check for if-then-else: blocks between cond+1 and target, last one
    # has an unconditional jump past target (skipping else body)
    last_then_idx = target_idx - 1
    if last_then_idx > cond_block_idx:
        last_then = blocks[last_then_idx]
        if isinstance(last_then.terminal, Jump):
            else_end_idx = name_to_idx.get(last_then.terminal.target)
            if else_end_idx is not None and else_end_idx > target_idx and else_end_idx <= region_end:
                # if/else pattern detected
                try:
                    then_body = _structure_region(
                        blocks, cond_block_idx + 1, last_then_idx, name_to_idx)
                    # Add last_then's statements (without the jump)
                    for stmt in last_then.stmts:
                        then_body.append(_wrap_stmt(stmt))
                    else_body = _structure_region(
                        blocks, target_idx, else_end_idx, name_to_idx)
                    node = SIf(_negate_expr(condition), then_body, else_body)
                    return (node, else_end_idx)
                except _UnstructurableError:
                    pass

    # Simple if-then (no else): condition true jumps past the then body
    try:
        then_body = _structure_region(
            blocks, cond_block_idx + 1, target_idx, name_to_idx)
        node = SIf(_negate_expr(condition), then_body, None)
        return (node, target_idx)
    except _UnstructurableError:
        return None


def _get_jump_targets(block, name_to_idx):
    """Get the block indices of all jump targets from a block."""
    targets = []
    if isinstance(block.terminal, Jump):
        idx = name_to_idx.get(block.terminal.target)
        if idx is not None:
            targets.append(idx)
    elif isinstance(block.terminal, CondJump):
        idx = name_to_idx.get(block.terminal.target)
        if idx is not None:
            targets.append(idx)
    return targets


def _wrap_stmt(stmt):
    """Wrap a statement or ForRegion into a structured IR node."""
    if isinstance(stmt, ForRegion):
        body = [_wrap_stmt(s) for s in stmt.body]
        return SFor(stmt.for_stmt.var, stmt.for_stmt.start,
                     stmt.for_stmt.end, stmt.for_stmt.step, body)
    return SStmt(stmt)


# ============================================================
# Variable analysis
# ============================================================

def _collect_read_vars(program):
    """Collect all variable names that are READ in any expression.

    A variable is "read" if it appears in a VarRef, ArrayIndex, or
    ArraySubrange in an expression context (not as an assignment target).
    Variables that are only written to (declared, assigned, used as FOR
    iterators) but never read can be eliminated.
    """
    read_vars = set()

    def _walk_expr(expr):
        if expr is None:
            return
        match expr:
            case VarRef(name=n):
                read_vars.add(n)
            case ArrayIndex(name=n, index=idx):
                read_vars.add(n)
                _walk_expr(idx)
            case ArraySubrange(name=n, high=h, low=l):
                read_vars.add(n)
                _walk_expr(h)
                _walk_expr(l)
            case ArrayWhole(name=n):
                read_vars.add(n)
            case BinOp(left=a, right=b):
                _walk_expr(a)
                _walk_expr(b)
            case UnaryOp(operand=a):
                _walk_expr(a)
            case FuncCall(arg=a):
                _walk_expr(a)

    def _walk_stmt(stmt):
        match stmt:
            case AssignStmt(target=_, index=idx, high=h, low=l, value=v):
                # target is a write, but index/subrange/value are reads
                _walk_expr(idx)
                _walk_expr(h)
                _walk_expr(l)
                _walk_expr(v)
            case IfStmt(condition=c, then_stmt=t):
                _walk_expr(c)
                _walk_stmt(t)
            case ForStmt(start=s, end=e, step=st):
                _walk_expr(s)
                _walk_expr(e)
                if st:
                    _walk_expr(st)
            case GotoStmt() | NextStmt():
                pass
            case CallStmt():
                pass
            case ExitStmt(code=c):
                _walk_expr(c)
            case PrintStmt(parts=parts):
                for p in parts:
                    if not isinstance(p, str):
                        _walk_expr(p)
            case ExportStmt(value=v):
                _walk_expr(v)
            case DrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r):
                _walk_expr(l)
                _walk_expr(t)
                # capture/compare/mask/result are array refs (writes + reads)
                if c: _walk_expr(c)
                if cmp: _walk_expr(cmp)
                if m: _walk_expr(m)
                if r: _walk_expr(r)
            case IrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r):
                _walk_expr(l)
                _walk_expr(t)
                if c: _walk_expr(c)
                if cmp: _walk_expr(cmp)
                if m: _walk_expr(m)
                if r: _walk_expr(r)
            case PreDrStmt(count=c, data=d) | PostDrStmt(count=c, data=d) | \
                 PreIrStmt(count=c, data=d) | PostIrStmt(count=c, data=d):
                _walk_expr(c)
                _walk_expr(d)
            case WaitStmt(cycles=c, usecs=u):
                if c: _walk_expr(c)
                if u: _walk_expr(u)
            case PushStmt(value=v):
                _walk_expr(v)

    for proc in program.procedures.values():
        for stmt in proc.statements:
            _walk_stmt(stmt)
            # Also walk IfStmt conditions that contain GOTOs
            # (these become CondJump terminals in blocks, but the
            # condition expression still reads variables)
            if isinstance(stmt, IfStmt):
                _walk_expr(stmt.condition)

    for data_block in program.data_blocks.values():
        for stmt in data_block.statements:
            # DATA block declarations: init expressions reference variables
            if isinstance(stmt, IntegerDecl) and stmt.init:
                for v in stmt.init:
                    _walk_expr(v)
            elif isinstance(stmt, BooleanDecl) and stmt.size:
                _walk_expr(stmt.size)

    return read_vars


def _collect_read_vars_simplified(program, constants):
    """Like _collect_read_vars, but simplifies expressions first.

    After constant propagation, some variable references disappear
    (e.g. `x or V100` where V100=0 simplifies to just `x`).
    """
    def simplify(expr):
        if expr is None:
            return expr
        match expr:
            case VarRef(name=n) if n in constants:
                return IntLiteral(value=constants[n])
            case UnaryOp(op=op, operand=inner):
                s = simplify(inner)
                if isinstance(s, IntLiteral):
                    v = _try_const_fold(UnaryOp(op=op, operand=s))
                    if v is not None:
                        return IntLiteral(value=v)
                return UnaryOp(op=op, operand=s)
            case BinOp(op=op, left=left, right=right):
                sl, sr = simplify(left), simplify(right)
                if isinstance(sl, IntLiteral) and isinstance(sr, IntLiteral):
                    v = _try_const_fold(BinOp(op=op, left=sl, right=sr))
                    if v is not None:
                        return IntLiteral(value=v)
                match op:
                    case '||':
                        if isinstance(sl, IntLiteral):
                            return IntLiteral(value=1) if sl.value else sr
                        if isinstance(sr, IntLiteral):
                            return IntLiteral(value=1) if sr.value else sl
                    case '&&':
                        if isinstance(sl, IntLiteral):
                            return sr if sl.value else IntLiteral(value=0)
                        if isinstance(sr, IntLiteral):
                            return sl if sr.value else IntLiteral(value=0)
                    case '|':
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return sr
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return sl
                    case '&':
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return IntLiteral(value=0)
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return IntLiteral(value=0)
                    case '+':
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return sr
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return sl
                    case '*':
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return IntLiteral(value=0)
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return IntLiteral(value=0)
                return BinOp(op=op, left=sl, right=sr)
            case FuncCall(name=n, arg=a):
                return FuncCall(name=n, arg=simplify(a))
            case ArrayIndex(name=n, index=idx):
                return ArrayIndex(name=n, index=simplify(idx))
            case ArraySubrange(name=n, high=h, low=l):
                return ArraySubrange(name=n, high=simplify(h), low=simplify(l))
        return expr

    read_vars = set()

    def walk(expr):
        if expr is None:
            return
        match expr:
            case VarRef(name=n):
                read_vars.add(n)
            case ArrayIndex(name=n, index=idx):
                read_vars.add(n)
                walk(idx)
            case ArraySubrange(name=n, high=h, low=l):
                read_vars.add(n)
                walk(h)
                walk(l)
            case ArrayWhole(name=n):
                read_vars.add(n)
            case BinOp(left=a, right=b):
                walk(a)
                walk(b)
            case UnaryOp(operand=a):
                walk(a)
            case FuncCall(arg=a):
                walk(a)

    def walk_stmt(stmt):
        match stmt:
            case AssignStmt(index=idx, high=h, low=l, value=v):
                walk(simplify(idx))
                walk(simplify(h))
                walk(simplify(l))
                walk(simplify(v))
            case IfStmt(condition=c, then_stmt=t):
                sc = simplify(c)
                if isinstance(sc, IntLiteral):
                    if sc.value:
                        walk_stmt(t)
                    # else: dead branch, don't walk
                else:
                    walk(sc)
                    walk_stmt(t)
            case ForStmt(start=s, end=e, step=st):
                walk(simplify(s))
                walk(simplify(e))
                if st: walk(simplify(st))
            case ExitStmt(code=c):
                walk(simplify(c))
            case PrintStmt(parts=parts):
                for p in parts:
                    if not isinstance(p, str):
                        walk(simplify(p))
            case ExportStmt(value=v):
                walk(simplify(v))
            case PushStmt(value=v):
                walk(simplify(v))
            case DrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r) | \
                 IrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r):
                for e in (l, t, c, cmp, m, r):
                    walk(simplify(e))
            case PreDrStmt(count=c, data=d) | PostDrStmt(count=c, data=d) | \
                 PreIrStmt(count=c, data=d) | PostIrStmt(count=c, data=d):
                walk(simplify(c))
                if d: walk(simplify(d))
            case WaitStmt(cycles=c, usecs=u):
                if c: walk(simplify(c))
                if u: walk(simplify(u))

    for proc in program.procedures.values():
        for stmt in proc.statements:
            walk_stmt(stmt)

    return read_vars


def _find_demotable_vars(program):
    """Find DATA variables that can be demoted to procedure locals.

    A variable can be demoted if, in every procedure that uses it,
    it is unconditionally written before any read. This means the
    value at procedure entry never matters, so it can be a local.

    Returns a set of variable names that can be demoted.
    """

    def _expr_reads(expr):
        """Collect variable names read by an expression."""
        names = set()
        if expr is None:
            return names
        match expr:
            case VarRef(name=n):
                names.add(n)
            case ArrayIndex(name=n, index=idx):
                names.add(n)
                names |= _expr_reads(idx)
            case ArraySubrange(name=n, high=h, low=l):
                names.add(n)
                names |= _expr_reads(h)
                names |= _expr_reads(l)
            case ArrayWhole(name=n):
                names.add(n)
            case BinOp(left=a, right=b):
                names |= _expr_reads(a)
                names |= _expr_reads(b)
            case UnaryOp(operand=a):
                names |= _expr_reads(a)
            case FuncCall(arg=a):
                names |= _expr_reads(a)
        return names

    def _stmt_reads(stmt):
        """Collect variable names read by a statement (not written)."""
        reads = set()
        match stmt:
            case AssignStmt(index=idx, high=h, low=l, value=v):
                reads |= _expr_reads(idx)
                reads |= _expr_reads(h)
                reads |= _expr_reads(l)
                reads |= _expr_reads(v)
            case IfStmt(condition=c, then_stmt=t):
                reads |= _expr_reads(c)
                reads |= _stmt_reads(t)
            case ForStmt(start=s, end=e, step=st):
                reads |= _expr_reads(s)
                reads |= _expr_reads(e)
                if st:
                    reads |= _expr_reads(st)
            case ExitStmt(code=c):
                reads |= _expr_reads(c)
            case PrintStmt(parts=parts):
                for p in parts:
                    if not isinstance(p, str):
                        reads |= _expr_reads(p)
            case ExportStmt(value=v):
                reads |= _expr_reads(v)
            case PushStmt(value=v):
                reads |= _expr_reads(v)
            case DrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r) | \
                 IrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r):
                reads |= _expr_reads(l)
                reads |= _expr_reads(t)
                if c: reads |= _expr_reads(c)
                if cmp: reads |= _expr_reads(cmp)
                if m: reads |= _expr_reads(m)
                if r: reads |= _expr_reads(r)
            case PreDrStmt(count=c, data=d) | PostDrStmt(count=c, data=d) | \
                 PreIrStmt(count=c, data=d) | PostIrStmt(count=c, data=d):
                reads |= _expr_reads(c)
                if d: reads |= _expr_reads(d)
            case WaitStmt(cycles=c, usecs=u):
                if c: reads |= _expr_reads(c)
                if u: reads |= _expr_reads(u)
        return reads

    def _stmt_writes(stmt):
        """Get variable name unconditionally written by a statement, or None."""
        match stmt:
            case AssignStmt(target=t, index=None, high=None):
                # Whole variable assignment (not indexed/subrange)
                return t
            case ForStmt(var=v):
                return v
            case PopStmt(target=t, index=None):
                return t
        return None

    def _analyze_proc(proc, data_vars):
        """Analyze one procedure. Return set of vars that need entry value."""
        needs_entry = set()
        definitely_written = set()

        for stmt in proc.statements:
            # Labels mean we could jump here from elsewhere, so
            # we can't trust that prior writes happened
            # (conservative: clear definitely_written)
            # But actually, labels are jump targets — code before a
            # label might be skipped. So any var only written before
            # a label isn't reliably written.
            # We handle this by stopping analysis at labels.

            # Check for labels at this statement index
            # (labels are stored in proc.labels as {name: stmt_index})

            reads = _stmt_reads(stmt) & data_vars
            for r in reads:
                if r not in definitely_written:
                    needs_entry.add(r)

            # Only count unconditional writes
            # (assignments inside IF don't count)
            written = _stmt_writes(stmt)
            if written and written in data_vars:
                definitely_written.add(written)

            # If we hit a GOTO or CALL, be conservative:
            # GOTO can jump backward (loop) or forward (skip),
            # CALL can do anything
            if isinstance(stmt, (GotoStmt, CallStmt)):
                break

        return needs_entry

    # Collect DATA variables per data block
    all_data_vars = set()
    for data_block in program.data_blocks.values():
        for stmt in data_block.statements:
            if isinstance(stmt, (IntegerDecl, BooleanDecl)):
                all_data_vars.add(stmt.name)

    if not all_data_vars:
        return set()

    # For each variable, track whether we've proven it's locally scoped
    # in every procedure, or if any procedure needs the entry value.
    #
    # A variable is demotable if, in every procedure that USES it,
    # it is unconditionally written before any read.
    #
    # Strategy: start with all DATA vars as candidates, then remove
    # any that fail the test in any procedure.
    candidates = set(all_data_vars)

    for proc in program.procedures.values():
        proc_data_vars = set()
        for data_name in proc.uses:
            db = program.data_blocks.get(data_name)
            if db:
                for stmt in db.statements:
                    if isinstance(stmt, (IntegerDecl, BooleanDecl)):
                        proc_data_vars.add(stmt.name)
        if not proc_data_vars:
            continue

        # Collect all variables actually referenced in this procedure
        all_reads = set()
        all_writes = set()
        for stmt in proc.statements:
            all_reads |= _stmt_reads(stmt) & proc_data_vars
            w = _stmt_writes(stmt)
            if w and w in proc_data_vars:
                all_writes.add(w)
            # Also count target of indexed/subrange assigns as writes
            if isinstance(stmt, AssignStmt) and stmt.target in proc_data_vars:
                all_writes.add(stmt.target)

        used_vars = (all_reads | all_writes) & candidates

        if not used_vars:
            continue

        label_indices = set(proc.labels.values())

        # If there's a label at index 0, we can't reason about anything
        if 0 in label_indices:
            candidates -= used_vars
            continue

        # Find the first label index
        first_label = min(label_indices) if label_indices else len(proc.statements)

        # Analyze the prefix before the first label/goto/call
        needs_entry = set()
        definitely_written = set()

        for i, stmt in enumerate(proc.statements):
            if i >= first_label:
                break

            reads = _stmt_reads(stmt) & used_vars
            for r in reads:
                if r not in definitely_written:
                    needs_entry.add(r)

            written = _stmt_writes(stmt)
            if written and written in used_vars:
                definitely_written.add(written)

            if isinstance(stmt, (GotoStmt, CallStmt)):
                break

        # Variables read before write need self
        candidates -= needs_entry
        # Variables used but not resolved in the prefix: be conservative
        unresolved = used_vars - definitely_written - needs_entry
        candidates -= unresolved

    return candidates


def _find_var_proc_map(program):
    """Map each DATA variable to the set of procedures that reference it.

    A variable is "referenced" if it appears in any expression or as
    an assignment target in the procedure's statements.
    """
    # Collect all DATA variable names
    data_vars = set()
    for db in program.data_blocks.values():
        for stmt in db.statements:
            if isinstance(stmt, (IntegerDecl, BooleanDecl)):
                data_vars.add(stmt.name)

    if not data_vars:
        return {}

    def _expr_names(expr):
        names = set()
        if expr is None:
            return names
        match expr:
            case VarRef(name=n) | ArrayIndex(name=n) | \
                 ArraySubrange(name=n) | ArrayWhole(name=n):
                names.add(n)
            case _:
                pass
        match expr:
            case ArrayIndex(index=idx):
                names |= _expr_names(idx)
            case ArraySubrange(high=h, low=l):
                names |= _expr_names(h)
                names |= _expr_names(l)
            case BinOp(left=a, right=b):
                names |= _expr_names(a)
                names |= _expr_names(b)
            case UnaryOp(operand=a) | FuncCall(arg=a):
                names |= _expr_names(a)
        return names

    def _stmt_names(stmt):
        names = set()
        match stmt:
            case AssignStmt(target=t, index=idx, high=h, low=l, value=v):
                names.add(t)
                names |= _expr_names(idx)
                names |= _expr_names(h)
                names |= _expr_names(l)
                names |= _expr_names(v)
            case ForStmt(var=v, start=s, end=e, step=st):
                names.add(v)
                names |= _expr_names(s)
                names |= _expr_names(e)
                if st: names |= _expr_names(st)
            case IfStmt(condition=c, then_stmt=t):
                names |= _expr_names(c)
                names |= _stmt_names(t)
            case PopStmt(target=t, index=idx):
                names.add(t)
                names |= _expr_names(idx)
            case PushStmt(value=v) | ExitStmt(code=v):
                names |= _expr_names(v)
            case PrintStmt(parts=parts):
                for p in parts:
                    if not isinstance(p, str):
                        names |= _expr_names(p)
            case ExportStmt(value=v):
                names |= _expr_names(v)
            case DrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r) | \
                 IrScanStmt(length=l, tdi=t, capture=c, compare=cmp, mask=m, result=r):
                for e in (l, t, c, cmp, m, r):
                    names |= _expr_names(e)
            case PreDrStmt(count=c, data=d) | PostDrStmt(count=c, data=d) | \
                 PreIrStmt(count=c, data=d) | PostIrStmt(count=c, data=d):
                names |= _expr_names(c)
                if d: names |= _expr_names(d)
            case WaitStmt(cycles=c, usecs=u):
                if c: names |= _expr_names(c)
                if u: names |= _expr_names(u)
        return names

    var_procs = {n: set() for n in data_vars}
    for proc_name, proc in program.procedures.items():
        # Which data vars does this proc have access to?
        proc_data = set()
        for dn in proc.uses:
            db = program.data_blocks.get(dn)
            if db:
                for stmt in db.statements:
                    if isinstance(stmt, (IntegerDecl, BooleanDecl)):
                        proc_data.add(stmt.name)
        if not proc_data:
            continue

        # Find which of those are actually referenced
        for stmt in proc.statements:
            referenced = _stmt_names(stmt) & proc_data
            for n in referenced:
                var_procs[n].add(proc_name)

    return var_procs


def _analyze_variables(program, config):
    """Analyze all variables in the program.

    Returns:
        (var_infos, data_files) where:
        - var_infos: dict[str, VarInfo]
        - data_files: dict[str, bytes] (filename → binary data for large booleans)
    """
    var_infos = {}
    data_files = {}
    # Map data content to filename for deduplication
    _data_content_to_file = {}

    # Collect DATA block variables
    for block_name, data_block in program.data_blocks.items():
        for stmt in data_block.statements:
            vi = _analyze_decl(stmt, 'data', block_name)
            if vi:
                var_infos[vi.name] = vi
                # Check if this should be an external file
                if (vi.vtype == 'boolean' and vi.init_data is not None
                        and vi.init_bit_count is not None
                        and vi.init_bit_count >= config.data_threshold):
                    if vi.init_data in _data_content_to_file:
                        vi.extern_filename = _data_content_to_file[vi.init_data]
                    else:
                        vi.extern_filename = f"{vi.name}.bin"
                        data_files[vi.extern_filename] = vi.init_data
                        _data_content_to_file[vi.init_data] = vi.extern_filename
                    vi.init_data = None  # mark as externalized

    # Collect procedure-local variables
    for proc_name, proc in program.procedures.items():
        for stmt in proc.statements:
            if isinstance(stmt, (IntegerDecl, BooleanDecl)):
                vi = _analyze_decl(stmt, 'local', None)
                if vi and vi.name not in var_infos:
                    var_infos[vi.name] = vi

    # Mark dead variables (written but never read)
    read_vars = _collect_read_vars(program)
    for vi in var_infos.values():
        vi.is_read = vi.name in read_vars

    # Mark constants: DATA-scope variables with literal init that are
    # either never reassigned, or only reassigned the same constant value.
    #
    # written_in_procs: set of vars that are written with a non-constant
    # or different-from-init value (these can't be constants).
    # We defer the init-value comparison until we know the init value.
    written_in_procs = set()
    # For vars written only with constant values, track those values
    proc_write_values = {}  # name -> set of folded values (or None if non-const)

    def _check_write(stmt):
        """Check a statement (and nested IfStmt bodies) for variable writes."""
        if isinstance(stmt, AssignStmt) and stmt.target in var_infos:
            name = stmt.target
            if stmt.index is None and stmt.high is None:
                val = _try_const_fold(stmt.value)
                if val is not None:
                    proc_write_values.setdefault(name, set()).add(val)
                    return
            written_in_procs.add(name)
        elif isinstance(stmt, IfStmt):
            _check_write(stmt.then_stmt)
        elif isinstance(stmt, ForStmt) and stmt.var in var_infos:
            written_in_procs.add(stmt.var)
        elif isinstance(stmt, PopStmt) and stmt.target in var_infos:
            written_in_procs.add(stmt.target)
        elif isinstance(stmt, (DrScanStmt, IrScanStmt)):
            if stmt.capture is not None:
                cap = stmt.capture
                name = getattr(cap, 'name', None)
                if name and name in var_infos:
                    written_in_procs.add(name)

    for proc in program.procedures.values():
        for stmt in proc.statements:
            _check_write(stmt)

    for vi in var_infos.values():
        if (vi.scope == 'data' and vi.has_init
                and vi.name not in written_in_procs and vi.is_read):
            if vi.vtype == 'integer':
                for block in program.data_blocks.values():
                    for stmt in block.statements:
                        if (isinstance(stmt, IntegerDecl) and stmt.name == vi.name
                                and stmt.init):
                            folded = [_try_const_fold(v) for v in stmt.init]
                            if all(v is not None for v in folded):
                                if vi.is_array:
                                    init_val = list(reversed(folded))
                                else:
                                    init_val = folded[0]
                                # Check proc writes match init value
                                write_vals = proc_write_values.get(vi.name)
                                if write_vals is None or write_vals == {init_val}:
                                    vi.is_const = True
                                    vi.const_value = init_val
                            break
            elif vi.vtype == 'boolean' and not vi.is_array:
                for block in program.data_blocks.values():
                    for stmt in block.statements:
                        if (isinstance(stmt, BooleanDecl) and stmt.name == vi.name
                                and stmt.init is not None
                                and not isinstance(stmt.init, BooleanLiteral)):
                            val = _try_const_fold(stmt.init)
                            if val is not None:
                                write_vals = proc_write_values.get(vi.name)
                                if write_vals is None or write_vals == {val}:
                                    vi.is_const = True
                                    vi.const_value = val
                            break

    # Re-check which variables are still read after constant propagation.
    # Constants get substituted in _simplify, so variables that were only
    # referenced in expressions alongside constants may no longer be needed.
    constants = {n: vi.const_value for n, vi in var_infos.items()
                 if vi.is_const and not vi.is_array}
    if constants:
        post_read = _collect_read_vars_simplified(program, constants)
        for vi in var_infos.values():
            if vi.is_read and not vi.is_const and vi.name not in post_read:
                vi.is_read = False

    # Prune data files for dead variables
    referenced_files = {vi.extern_filename for vi in var_infos.values()
                        if vi.is_read and vi.extern_filename is not None}
    data_files = {k: v for k, v in data_files.items() if k in referenced_files}

    return var_infos, data_files


def _analyze_decl(stmt, scope, data_block):
    """Analyze a variable declaration statement."""
    if isinstance(stmt, IntegerDecl):
        is_array = stmt.size is not None
        size = None
        if is_array and isinstance(stmt.size, IntLiteral):
            size = stmt.size.value
        return VarInfo(
            name=stmt.name,
            vtype='integer',
            is_array=is_array,
            size=size,
            has_init=stmt.init is not None,
            init_data=None,
            init_bit_count=None,
            scope=scope,
            data_block=data_block,
        )
    elif isinstance(stmt, BooleanDecl):
        is_array = stmt.size is not None
        size = None
        if is_array and isinstance(stmt.size, IntLiteral):
            size = stmt.size.value
        init_data = None
        init_bit_count = None
        if stmt.init is not None and isinstance(stmt.init, BooleanLiteral):
            init_data = stmt.init.data
            init_bit_count = stmt.init.bit_count
        return VarInfo(
            name=stmt.name,
            vtype='boolean',
            is_array=is_array,
            size=size,
            has_init=stmt.init is not None,
            init_data=init_data,
            init_bit_count=init_bit_count,
            scope=scope,
            data_block=data_block,
        )
    return None


# ============================================================
# Python code writer
# ============================================================

class _Writer:
    """Indentation-aware code writer."""

    def __init__(self):
        self._lines = []
        self._indent = 0

    def line(self, text=''):
        if text:
            self._lines.append('    ' * self._indent + text)
        else:
            self._lines.append('')

    def indent(self):
        self._indent += 1

    def dedent(self):
        self._indent -= 1

    def text(self):
        return '\n'.join(self._lines) + '\n'


# ============================================================
# Expression emission
# ============================================================

class _ExprEmitter:
    """Emit Python expressions from STAPL AST expressions."""

    # Python operator precedence (higher = binds tighter)
    # From Python docs (low to high):
    # or < and < not < comparisons < | < ^ < & < shifts < +- < */% < unary
    _PRECEDENCE = {
        '||': 4, 'or': 4,
        '&&': 5, 'and': 5,
        '!': 6, 'not': 6,
        '==': 7, '!=': 7, '<': 7, '>': 7, '<=': 7, '>=': 7,
        '|': 8,
        '^': 9,
        '&': 10,
        '<<': 11, '>>': 11,
        '+': 12, '-': 12,
        '*': 13, '/': 13, '//': 13, '%': 13,
        '~': 14,
        'UMINUS': 14,
    }

    def __init__(self, var_infos, local_vars, config=None):
        self._var_infos = var_infos
        self._local_vars = local_vars  # set of names declared locally
        self._constants = {n: vi.const_value for n, vi in var_infos.items()
                           if vi.is_const and not vi.is_array}
        # Build variable → enum/bitfield type maps
        self._var_enum = {}  # var name → EnumDef
        self._var_bitfield = {}  # var name → BitfieldDef
        if config:
            for edef in config.enums:
                for vname in edef.variables:
                    self._var_enum[vname] = edef
            for bdef in config.bitfields:
                for vname in bdef.variables:
                    self._var_bitfield[vname] = bdef

    def _ref(self, name):
        """Variable reference: self.NAME for data, NAME for locals."""
        if name in self._local_vars:
            return name
        return f'self.{name}'

    def _is_boolean_array(self, name):
        vi = self._var_infos.get(name)
        return vi is not None and vi.vtype == 'boolean' and vi.is_array

    def _fmt_typed_int(self, value, type_hint=None):
        """Format an integer literal, using enum/bitfield names if available."""
        if isinstance(type_hint, EnumDef) and value in type_hint.values:
            return f'{type_hint.class_name}.{type_hint.values[value]}'
        if isinstance(type_hint, BitfieldDef):
            return self._fmt_flags(value, type_hint)
        if abs(value) > 255:
            return f'0x{value:X}' if value >= 0 else f'-0x{-value:X}'
        return str(value)

    def _fmt_flags(self, value, bdef):
        """Format an integer as a combination of bitfield flags."""
        if value == 0:
            return '0'
        # Negative value: try ~value as flag complement (used in & ~FLAG patterns)
        if value < 0:
            inv = ~value
            inv_fmt = self._fmt_flags_positive(inv, bdef)
            if inv_fmt is not None:
                return f'~{inv_fmt}' if ' ' not in inv_fmt else f'~({inv_fmt})'
        if value > 0:
            fmt = self._fmt_flags_positive(value, bdef)
            if fmt is not None:
                return fmt
        if abs(value) > 255:
            return f'0x{value:X}' if value >= 0 else f'-0x{-value:X}'
        return str(value)

    def _fmt_flags_positive(self, value, bdef):
        """Try to format a positive value as flag combination. Returns None if no flags match."""
        parts = []
        remaining = value
        for mask in sorted(bdef.values.keys(), reverse=True):
            if remaining & mask == mask:
                parts.append(f'{bdef.class_name}.{bdef.values[mask]}')
                remaining &= ~mask
        if remaining:
            if parts:
                parts.append(f'0x{remaining:X}' if remaining > 255 else str(remaining))
            else:
                return None
        if not parts:
            return None
        result = ' | '.join(parts)
        # Wrap in parens if multiple flags (needed for & precedence)
        if len(parts) > 1:
            result = f'({result})'
        return result

    def _type_for_var(self, name):
        """Get the enum/bitfield type for a variable, if any."""
        if name in self._var_enum:
            return self._var_enum[name]
        if name in self._var_bitfield:
            return self._var_bitfield[name]
        return None

    def _infer_type(self, expr):
        """Infer enum/bitfield type from an expression (variable ref or array index)."""
        match expr:
            case VarRef(name=n):
                return self._type_for_var(n)
            case ArrayIndex(name=n):
                return self._type_for_var(n)
        return None

    def _simplify(self, expr):
        """Simplify an expression: fold constants, propagate known values,
        apply algebraic identities."""
        match expr:
            case VarRef(name=n) if n in self._constants:
                return IntLiteral(value=self._constants[n])

            case UnaryOp(op='!', operand=inner):
                s = self._simplify(inner)
                if isinstance(s, IntLiteral):
                    return IntLiteral(value=int(not s.value))
                return UnaryOp(op='!', operand=s)

            case UnaryOp(op=op, operand=inner):
                s = self._simplify(inner)
                match op:
                    case '-' if isinstance(s, IntLiteral):
                        return IntLiteral(value=-s.value)
                    case '~' if isinstance(s, IntLiteral):
                        return IntLiteral(value=~s.value)
                return UnaryOp(op=op, operand=s)

            case BinOp(op=op, left=left, right=right):
                sl = self._simplify(left)
                sr = self._simplify(right)
                # Full constant fold
                if isinstance(sl, IntLiteral) and isinstance(sr, IntLiteral):
                    val = _try_const_fold(BinOp(op=op, left=sl, right=sr))
                    if val is not None:
                        return IntLiteral(value=val)
                # Algebraic identities for logical operators
                match op:
                    case '||':
                        if isinstance(sl, IntLiteral):
                            return IntLiteral(value=1) if sl.value else sr
                        if isinstance(sr, IntLiteral):
                            return IntLiteral(value=1) if sr.value else sl
                    case '&&':
                        if isinstance(sl, IntLiteral):
                            return sr if sl.value else IntLiteral(value=0)
                        if isinstance(sr, IntLiteral):
                            return sl if sr.value else IntLiteral(value=0)
                    case '|':
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return sr
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return sl
                    case '&':
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return IntLiteral(value=0)
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return IntLiteral(value=0)
                    case '+':
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return sr
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return sl
                    case '*':
                        if isinstance(sl, IntLiteral) and sl.value == 1:
                            return sr
                        if isinstance(sr, IntLiteral) and sr.value == 1:
                            return sl
                        if isinstance(sl, IntLiteral) and sl.value == 0:
                            return IntLiteral(value=0)
                        if isinstance(sr, IntLiteral) and sr.value == 0:
                            return IntLiteral(value=0)
                return BinOp(op=op, left=sl, right=sr)

            case FuncCall(name=n, arg=a):
                return FuncCall(name=n, arg=self._simplify(a))

            case ArrayIndex(name=n, index=idx):
                return ArrayIndex(name=n, index=self._simplify(idx))

            case ArraySubrange(name=n, high=h, low=l):
                return ArraySubrange(name=n,
                                     high=self._simplify(h),
                                     low=self._simplify(l))

        return expr

    def _exclusive_end(self, expr):
        """Emit expr + 1 with simplification for slice exclusive end."""
        match expr:
            case BinOp(op='-', left=a, right=IntLiteral(value=1)):
                return self.int_expr(a)
            case IntLiteral(value=v):
                return self.int_expr(IntLiteral(value=v + 1))
            case _:
                return f'{self.int_expr(expr)} + 1'

    def _exclusive_end_rev(self, expr):
        """Emit expr - 1 with simplification for reversed slice stop."""
        match expr:
            case BinOp(op='+', left=a, right=IntLiteral(value=1)):
                return self.int_expr(a)
            case IntLiteral(value=0):
                return None  # will need special handling
            case IntLiteral(value=v):
                return self.int_expr(IntLiteral(value=v - 1))
            case _:
                return f'{self.int_expr(expr)} - 1'

    def slice_expr(self, high, low):
        """Emit slice for a[high..low] subrange (STAPL convention).

        Returns a string like '[0:10]' or '[3::-1]'.
        Uses _try_const_fold to determine direction statically.
        Falls back to get_subrange() for dynamic cases.
        """
        h_val = _try_const_fold(high)
        l_val = _try_const_fold(low)

        if h_val is not None and l_val is not None:
            if h_val >= l_val:
                # Ascending: a[low:high+1]
                return f'[{self.int_expr(low)}:{self._exclusive_end(high)}]'
            else:
                # Reversed: a[low:high-1:-1] (or a[low::-1] when high=0)
                stop = self._exclusive_end_rev(high)
                if stop is None:
                    return f'[{self.int_expr(low)}::-1]'
                return f'[{self.int_expr(low)}:{stop}:-1]'
        else:
            # Dynamic: cannot determine direction at compile time
            # Emit ascending and hope for the best (all real STAPL uses ascending)
            return f'[{self.int_expr(low)}:{self._exclusive_end(high)}]'

    def int_expr(self, expr, _parent_prec=0, _type_hint=None):
        """Emit expression that evaluates to int.

        _parent_prec is the precedence of the enclosing operator.
        _type_hint is an EnumDef or BitfieldDef for contextual formatting.
        """
        expr = self._simplify(expr)
        return self._emit_int(expr, _parent_prec, _type_hint)

    def _emit_int(self, expr, parent_prec=0, type_hint=None):
        """Emit an already-simplified expression."""
        match expr:
            case IntLiteral(value=v):
                return self._fmt_typed_int(v, type_hint)

            case VarRef(name=n):
                return self._ref(n)

            case ArrayIndex(name=n, index=idx):
                arr = self._ref(n)
                return f'{arr}[{self._emit_int(idx)}]'

            case ArraySubrange(name=n, high=h, low=l):
                arr = self._ref(n)
                return f'{arr}{self.slice_expr(h, l)}.to_int()'

            case ArrayWhole(name=n):
                arr = self._ref(n)
                if self._is_boolean_array(n):
                    return f'{arr}.to_int()'
                return arr

            case UnaryOp(op='!', operand=a):
                my_prec = self._PRECEDENCE.get('not', 0)
                inner = self._emit_int(a, my_prec)
                s = f'not {inner}'
                return f'({s})' if my_prec < parent_prec else s

            case UnaryOp(op=op, operand=a):
                my_prec = self._PRECEDENCE.get('UMINUS' if op == '-' else op, 0)
                inner = self._emit_int(a, my_prec)
                s = f'{op}{inner}'
                return f'({s})' if my_prec < parent_prec else s

            case BinOp(op='&&' | '||' as op, left=a, right=b):
                py_op = 'and' if op == '&&' else 'or'
                my_prec = self._PRECEDENCE.get(py_op, 0)
                left_s = self._emit_int(a, my_prec)
                right_s = self._emit_int(b, my_prec + 1)
                s = f'{left_s} {py_op} {right_s}'
                return f'({s})' if my_prec < parent_prec else s

            case BinOp(op=op, left=a, right=b):
                py_op = '//' if op == '/' else op
                my_prec = self._PRECEDENCE.get(py_op, 0)
                # Infer type context from variable operands
                child_hint = type_hint
                if op in ('==', '!=', '<', '>', '<=', '>='):
                    child_hint = self._infer_type(a) or self._infer_type(b)
                elif op in ('&', '|', '^'):
                    child_hint = self._infer_type(a) or self._infer_type(b)
                left_s = self._emit_int(a, my_prec, child_hint)
                right_s = self._emit_int(b, my_prec + 1, child_hint)
                s = f'{left_s} {py_op} {right_s}'
                return f'({s})' if my_prec < parent_prec else s

            case FuncCall(name='ABS', arg=a):
                return f'abs({self._emit_int(a)})'

            case FuncCall(name='INT', arg=a):
                return self._int_of_bits(a)

            case FuncCall(name='CHR$', arg=a):
                return f'chr({self._emit_int(a)})'

            case FuncCall(name=n, arg=a):
                return f'{n}({self._emit_int(a)})'

            case BooleanLiteral(data=d, bit_count=bc):
                val = int.from_bytes(d, 'little')
                if val > 255:
                    return f'0x{val:X}'
                return str(val)

            case _:
                return repr(expr)

    def _int_of_bits(self, expr):
        """Emit int conversion of a bits expression."""
        match expr:
            case ArraySubrange(name=n, high=h, low=l):
                arr = self._ref(n)
                return f'{arr}{self.slice_expr(h, l)}.to_int()'
            case ArrayWhole(name=n):
                return f'{self._ref(n)}.to_int()'
            case VarRef(name=n):
                if self._is_boolean_array(n):
                    return f'{self._ref(n)}.to_int()'
                return self._ref(n)
            case _:
                return f'{self.bits_expr(expr)}.to_int()'

    def bits_expr(self, expr):
        """Emit expression that evaluates to BitArray."""
        match expr:
            case VarRef(name=n):
                return self._ref(n)

            case ArraySubrange(name=n, high=h, low=l):
                arr = self._ref(n)
                return f'{arr}{self.slice_expr(h, l)}'

            case ArrayWhole(name=n):
                return self._ref(n)

            case BooleanLiteral(data=d, bit_count=bc):
                return f'BitArray({bc}, {d!r})'

            case FuncCall(name='BOOL', arg=a):
                return f'BitArray.from_int({self.int_expr(a)})'

            case _:
                # Fallback: convert int expression to BitArray
                return f'BitArray.from_int({self.int_expr(expr)})'

    def scan_tdi_expr(self, expr):
        """Emit expression for scan TDI data (needs to produce bytes)."""
        return f'{self.bits_expr(expr)}.to_bytes()'

    def scan_tdi_as_int(self, expr):
        """Emit expression for IR scan (integer value)."""
        match expr:
            case BooleanLiteral(data=d, bit_count=bc):
                val = int.from_bytes(d, 'little') & ((1 << bc) - 1)
                if val > 255:
                    return f'0x{val:X}'
                return str(val)
            case _:
                return self._int_of_bits(expr)


# ============================================================
# Statement emission
# ============================================================

class _StmtEmitter:
    """Emit Python statements from structured IR."""

    def __init__(self, w, expr_em, var_infos, proc_locals, program):
        self._w = w
        self._dead_vars = {n for n, vi in var_infos.items()
                           if not vi.is_read}
        self._constants = {n: vi.const_value for n, vi in var_infos.items()
                           if vi.is_const and not vi.is_array}
        self._expr = expr_em
        self._var_infos = var_infos
        self._proc_locals = proc_locals
        self._program = program
        self._in_dispatch = False  # True when inside _emit_dispatch

    def emit_structured(self, nodes):
        """Emit a list of structured IR nodes."""
        for node in nodes:
            self._emit_node(node)

    def _emit_node(self, node):
        w = self._w
        match node:
            case SStmt(stmt=stmt):
                self._emit_plain_stmt(stmt)

            case SFor(var=var, start=start, end=end, step=step, body=body):
                ref = var if var in self._proc_locals else f'self.{var}'
                s = self._expr.int_expr(start)
                e = self._expr.int_expr(end)
                if step is None or (isinstance(step, IntLiteral) and step.value == 1):
                    w.line(f'for {ref} in range({s}, {e} + 1):')
                else:
                    st = self._expr.int_expr(step)
                    w.line(f'for {ref} in range({s}, {e} + 1, {st}):')
                w.indent()
                if body:
                    self.emit_structured(body)
                else:
                    w.line('pass')
                w.dedent()

            case SWhile(condition=cond, body=body):
                w.line(f'while {self._expr.int_expr(cond)}:')
                w.indent()
                if body:
                    self.emit_structured(body)
                else:
                    w.line('pass')
                w.dedent()

            case SWhileTrue(body=body):
                w.line('while True:')
                w.indent()
                if body:
                    self.emit_structured(body)
                else:
                    w.line('pass')
                w.dedent()

            case SIf(condition=cond, then_body=then_b, else_body=else_b):
                folded = _try_const_fold(cond, self._constants)
                if folded is not None:
                    if folded:
                        if then_b:
                            self.emit_structured(then_b)
                    else:
                        if else_b:
                            self.emit_structured(else_b)
                else:
                    w.line(f'if {self._expr.int_expr(cond)}:')
                    w.indent()
                    before = len(w._lines)
                    if then_b:
                        self.emit_structured(then_b)
                    if len(w._lines) == before:
                        w.line('pass')
                    w.dedent()
                    if else_b:
                        w.line('else:')
                        w.indent()
                        before = len(w._lines)
                        self.emit_structured(else_b)
                        if len(w._lines) == before:
                            w.line('pass')
                        w.dedent()

            case SBreak():
                w.line('break')

            case SContinue():
                w.line('continue')

            case SExit(code=code):
                w.line(f'raise _StaplExit({self._expr.int_expr(code)})')

            case SReturn():
                w.line('return')

            case SDispatch(entry=entry, blocks=blocks, name_to_idx=nti):
                self._emit_dispatch(entry, blocks)

            case _:
                w.line(f'# ??? {type(node).__name__}')

    def _emit_dispatch(self, entry, blocks):
        """Emit block dispatch fallback."""
        w = self._w
        old_in_dispatch = self._in_dispatch
        self._in_dispatch = True
        w.line(f'_block = {entry!r}')
        w.line('while _block is not None:')
        w.indent()
        w.line('match _block:')
        w.indent()
        for block in blocks:
            w.line(f'case {block.name!r}:')
            w.indent()
            lines_before = len(w._lines)
            for stmt in block.stmts:
                self._emit_plain_stmt(stmt)
            if len(w._lines) == lines_before:
                w.line('pass  # all statements eliminated (dead vars)')
            # Terminal
            match block.terminal:
                case Fallthrough():
                    next_idx = block.index + 1
                    if next_idx < len(blocks):
                        w.line(f'_block = {blocks[next_idx].name!r}')
                    else:
                        w.line('_block = None')
                case Jump(target=t):
                    w.line(f'_block = {t!r}')
                case CondJump(condition=c, target=t):
                    folded = _try_const_fold(c, self._constants)
                    next_idx = block.index + 1
                    if folded is not None:
                        if folded:
                            # Always true: jump unconditionally
                            w.line(f'_block = {t!r}')
                        else:
                            # Always false: fall through
                            if next_idx < len(blocks):
                                w.line(f'_block = {blocks[next_idx].name!r}')
                            else:
                                w.line('_block = None')
                    else:
                        w.line(f'if {self._expr.int_expr(c)}:')
                        w.indent()
                        w.line(f'_block = {t!r}')
                        w.dedent()
                        if next_idx < len(blocks):
                            w.line('else:')
                            w.indent()
                            w.line(f'_block = {blocks[next_idx].name!r}')
                            w.dedent()
                        else:
                            w.line('else:')
                            w.indent()
                            w.line('_block = None')
                            w.dedent()
                case BlockExit(code=c):
                    w.line(f'raise _StaplExit({self._expr.int_expr(c)})')
                case BlockReturn():
                    w.line('_block = None')
            w.dedent()
        w.line('case _:')
        w.indent()
        w.line('assert False, f"unknown block {_block}"')
        w.dedent()
        w.dedent()
        w.dedent()
        self._in_dispatch = old_in_dispatch

    def _emit_plain_stmt(self, stmt):
        """Emit a plain STAPL statement."""
        w = self._w
        e = self._expr

        match stmt:
            case IntegerDecl(name=n, size=sz, init=init) if n in self._dead_vars:
                pass  # dead variable, skip

            case IntegerDecl(name=n, size=sz, init=init):
                ref = n if n in self._proc_locals else f'self.{n}'
                if sz is not None:
                    size_s = e.int_expr(sz)
                    if init is not None:
                        # Altera reversal: last init value → index 0
                        vals = ', '.join(e.int_expr(v) for v in reversed(init))
                        w.line(f'{ref} = [{vals}]')
                    else:
                        w.line(f'{ref} = [0] * {size_s}')
                else:
                    if init is not None:
                        w.line(f'{ref} = {e.int_expr(init[0])}')
                    else:
                        w.line(f'{ref} = 0')

            case BooleanDecl(name=n, size=sz, init=init) if n in self._dead_vars:
                pass  # dead variable, skip

            case BooleanDecl(name=n, size=sz, init=init):
                ref = n if n in self._proc_locals else f'self.{n}'
                if sz is not None:
                    size_s = e.int_expr(sz)
                    if init is not None and isinstance(init, BooleanLiteral):
                        vi = self._var_infos.get(n)
                        if vi and vi.extern_filename is not None:
                            # Externalized to file
                            w.line(f'{ref} = BitArray({init.bit_count}, '
                                   f'(self.DATA_DIR / "{vi.extern_filename}").read_bytes())')
                        else:
                            # Inline
                            w.line(f'{ref} = BitArray({init.bit_count}, {init.data!r})')
                    else:
                        w.line(f'{ref} = BitArray({size_s})')
                else:
                    # Scalar boolean
                    if init is not None:
                        w.line(f'{ref} = {e.int_expr(init)}')
                    else:
                        w.line(f'{ref} = 0')

            case AssignStmt(target=t) if t in self._dead_vars:
                pass  # dead variable, skip assignment

            case AssignStmt(target=t, index=idx, high=h, low=l, value=v):
                ref = t if t in self._proc_locals else f'self.{t}'
                th = e._type_for_var(t)
                if h is not None and l is not None:
                    # Subrange assignment
                    w.line(f'{ref}{e.slice_expr(h, l)} = '
                           f'{e.bits_expr(v)}')
                elif idx is not None:
                    w.line(f'{ref}[{e.int_expr(idx)}] = '
                           f'{e.int_expr(v, _type_hint=th)}')
                else:
                    vi = self._var_infos.get(t)
                    if vi and vi.vtype == 'boolean' and vi.is_array:
                        w.line(f'{ref} = {e.bits_expr(v)}')
                    else:
                        w.line(f'{ref} = {e.int_expr(v, _type_hint=th)}')

            case CallStmt(procedure=p):
                w.line(f'self._proc_{p.lower()}()')

            case ExitStmt(code=c):
                w.line(f'raise _StaplExit({e.int_expr(c)})')

            case IfStmt(condition=c, then_stmt=AssignStmt(target=t2)) \
                    if t2 in self._dead_vars:
                pass  # if body is dead assignment, skip entire if

            case IfStmt(condition=c, then_stmt=t):
                folded = _try_const_fold(c, self._constants)
                if folded is not None:
                    if folded:
                        # Always true: emit body unconditionally
                        self._emit_plain_stmt(t)
                    # else: always false, skip entirely
                else:
                    w.line(f'if {e.int_expr(c)}:')
                    w.indent()
                    self._emit_plain_stmt(t)
                    w.dedent()

            case GotoStmt(label=l):
                if self._in_dispatch:
                    w.line(f'_block = {l!r}')
                    w.line('continue')
                else:
                    w.line(f'pass  # GOTO {l}')

            case PushStmt(value=v):
                w.line(f'self._stack.append({e.int_expr(v)})')

            case PopStmt(target=t, index=idx):
                ref = t if t in self._proc_locals else f'self.{t}'
                if idx is not None:
                    w.line(f'{ref}[{e.int_expr(idx)}] = self._stack.pop()')
                else:
                    w.line(f'{ref} = self._stack.pop()')

            case DrScanStmt(length=l, tdi=tdi, capture=cap, compare=cmp,
                            mask=m, result=r):
                self._emit_scan(False, l, tdi, cap, cmp, m, r)

            case IrScanStmt(length=l, tdi=tdi, capture=cap, compare=cmp,
                            mask=m, result=r):
                self._emit_scan(True, l, tdi, cap, cmp, m, r)

            case DrStopStmt(state=s):
                w.line(f'self._dr_stop = {s!r}')

            case IrStopStmt(state=s):
                w.line(f'self._ir_stop = {s!r}')

            case StateStmt(path=p):
                args = ', '.join(f'{s!r}' for s in p)
                w.line(f'self._state({args})')

            case WaitStmt(wait_state=ws, cycles=cy, usecs=us,
                          end_state=es):
                parts = []
                parts.append(f'{ws!r}' if ws else 'None')
                parts.append(e.int_expr(cy) if cy else 'None')
                parts.append(e.int_expr(us) if us else 'None')
                parts.append(f'{es!r}' if es else 'None')
                w.line(f'self._wait({", ".join(parts)})')

            case TrstStmt(cycles=cy, usecs=us):
                cy_s = e.int_expr(cy) if cy else 'None'
                us_s = e.int_expr(us) if us else 'None'
                w.line(f'self._trst({cy_s}, {us_s})')

            case FrequencyStmt(value=v):
                if v:
                    w.line(f'self._frequency({e.int_expr(v)})')
                else:
                    w.line(f'self._frequency(None)')

            case PreDrStmt(count=c, data=d):
                if d:
                    w.line(f'self._pre_dr = ({e.int_expr(c)}, {e.scan_tdi_expr(d)})')
                else:
                    w.line(f'self._pre_dr = ({e.int_expr(c)}, None)')

            case PostDrStmt(count=c, data=d):
                if d:
                    w.line(f'self._post_dr = ({e.int_expr(c)}, {e.scan_tdi_expr(d)})')
                else:
                    w.line(f'self._post_dr = ({e.int_expr(c)}, None)')

            case PreIrStmt(count=c, data=d):
                if d:
                    w.line(f'self._pre_ir = ({e.int_expr(c)}, {e.scan_tdi_expr(d)})')
                else:
                    w.line(f'self._pre_ir = ({e.int_expr(c)}, None)')

            case PostIrStmt(count=c, data=d):
                if d:
                    w.line(f'self._post_ir = ({e.int_expr(c)}, {e.scan_tdi_expr(d)})')
                else:
                    w.line(f'self._post_ir = ({e.int_expr(c)}, None)')

            case PrintStmt(parts=parts):
                args = []
                for p in parts:
                    if isinstance(p, str):
                        args.append(f'{p!r}')
                    else:
                        args.append(e.int_expr(p))
                w.line(f'print({", ".join(args)}, sep="")')

            case ExportStmt(key=k, value=v):
                w.line(f'self._export({k!r}, {e.int_expr(v)})')

            case ReturnStmt():
                w.line('return')

            case ForRegion(for_stmt=fs, body=body, next_stmt=ns):
                # ForRegion in dispatch mode: emit as for loop
                ref = fs.var if fs.var in self._proc_locals else f'self.{fs.var}'
                s = e.int_expr(fs.start)
                end_s = e.int_expr(fs.end)
                if fs.step is None or (isinstance(fs.step, IntLiteral) and fs.step.value == 1):
                    w.line(f'for {ref} in range({s}, {end_s} + 1):')
                else:
                    w.line(f'for {ref} in range({s}, {end_s} + 1, {e.int_expr(fs.step)}):')
                w.indent()
                for sub in body:
                    self._emit_plain_stmt(sub)
                if not body:
                    w.line('pass')
                w.dedent()

            case ForStmt(var=v, start=s, end=end, step=st):
                # Bare ForStmt (label inside FOR/NEXT, couldn't extract)
                ref = v if v in self._proc_locals else f'self.{v}'
                w.line(f'{ref} = {e.int_expr(s)}  # FOR {v}')

            case NextStmt(var=v):
                # Bare NextStmt
                ref = v if v in self._proc_locals else f'self.{v}'
                w.line(f'{ref} += 1  # NEXT {v}')

            case _:
                w.line(f'# ??? {type(stmt).__name__}')

    def _emit_scan(self, is_ir, length, tdi, capture, compare, mask, result):
        """Emit IR or DR scan."""
        w = self._w
        e = self._expr
        length_s = e.int_expr(length)

        if is_ir:
            # IRSCAN: emit as _ir_scan with integer value
            w.line(f'self._ir_scan({e.scan_tdi_as_int(tdi)}, {length_s})')
            if capture:
                w.line(f'# IR capture not supported in transpiled output')
        else:
            # DRSCAN
            has_capture = capture is not None or compare is not None
            if has_capture:
                w.line(f'_tdo = self._dr_scan('
                       f'{e.scan_tdi_expr(tdi)}, {length_s}, capture=True)')
                if capture is not None:
                    self._emit_capture_store(capture, length_s)
                if compare is not None:
                    cap_ref = self._emit_capture_ref(capture) if capture else '_tdo_bits'
                    if capture is None:
                        w.line(f'_tdo_bits = BitArray({length_s}, _tdo)')
                    cmp_s = e.bits_expr(compare)
                    mask_s = e.bits_expr(mask)
                    result_ref = self._emit_lvalue(result)
                    w.line(f'{result_ref} = 1 if {cap_ref}.compare('
                           f'{cmp_s}, {mask_s}, {length_s}) else 0')
            else:
                w.line(f'self._dr_scan('
                       f'{e.scan_tdi_expr(tdi)}, {length_s})')

    def _emit_capture_store(self, capture_expr, length_s):
        """Emit code to store captured TDO data."""
        w = self._w
        match capture_expr:
            case ArraySubrange(name=n, high=h, low=l):
                ref = n if n in self._proc_locals else f'self.{n}'
                w.line(f'{ref}{self._expr.slice_expr(h, l)} = '
                       f'BitArray({length_s}, _tdo)')
            case ArrayWhole(name=n):
                ref = n if n in self._proc_locals else f'self.{n}'
                w.line(f'{ref} = BitArray({length_s}, _tdo)')
            case VarRef(name=n):
                ref = n if n in self._proc_locals else f'self.{n}'
                w.line(f'{ref} = BitArray({length_s}, _tdo)')
            case _:
                w.line(f'# capture store: ??? {capture_expr!r}')

    def _emit_capture_ref(self, capture_expr):
        """Emit a reference to the captured data variable."""
        match capture_expr:
            case ArraySubrange(name=n):
                ref = n if n in self._proc_locals else f'self.{n}'
                return ref
            case ArrayWhole(name=n) | VarRef(name=n):
                ref = n if n in self._proc_locals else f'self.{n}'
                return ref
            case _:
                return '_tdo_bits'

    def _emit_lvalue(self, expr):
        """Emit an lvalue expression (assignment target)."""
        match expr:
            case VarRef(name=n):
                return n if n in self._proc_locals else f'self.{n}'
            case ArrayIndex(name=n, index=idx):
                ref = n if n in self._proc_locals else f'self.{n}'
                return f'{ref}[{self._expr.int_expr(idx)}]'
            case _:
                return f'# ??? lvalue {expr!r}'


# ============================================================
# Top-level file emission
# ============================================================

def _collect_proc_locals(proc):
    """Collect local variable names declared in a procedure."""
    locals_set = set()
    for stmt in proc.statements:
        if isinstance(stmt, IntegerDecl):
            locals_set.add(stmt.name)
        elif isinstance(stmt, BooleanDecl):
            locals_set.add(stmt.name)
    return locals_set


def _collect_data_vars(proc, program):
    """Collect variable names from DATA blocks that a procedure USES."""
    data_vars = set()
    for data_name in proc.uses:
        data_block = program.data_blocks.get(data_name)
        if data_block:
            for stmt in data_block.statements:
                if isinstance(stmt, (IntegerDecl, BooleanDecl)):
                    data_vars.add(stmt.name)
    return data_vars


def transpile(program: Program, config: TranspileConfig | None = None,
              source_name: str = "unknown") -> tuple[str, dict[str, bytes]]:
    """Transpile a STAPL program to Python source + data files.

    Args:
        program: Parsed STAPL Program.
        config: Transpilation options.
        source_name: Original filename for documentation.

    Returns:
        (python_source, data_files) where data_files maps
        "filename.bin" → bytes for external data.
    """
    if config is None:
        config = TranspileConfig()

    # Normalize USES references to match DATA block key casing
    # Normalize GOTO targets to match label declaration case
    # (STAPL is case-insensitive)
    for proc in program.procedures.values():
        proc.uses = [u.upper() for u in proc.uses]
        label_canon = {k.upper(): k for k in proc.labels}
        for stmt in proc.statements:
            if isinstance(stmt, GotoStmt) and stmt.label.upper() in label_canon:
                stmt.label = label_canon[stmt.label.upper()]
            elif (isinstance(stmt, IfStmt)
                    and isinstance(stmt.then_stmt, GotoStmt)
                    and stmt.then_stmt.label.upper() in label_canon):
                stmt.then_stmt.label = label_canon[stmt.then_stmt.label.upper()]

    if config.rename_map:
        program = _apply_rename_map(program, config.rename_map)
        # Apply renames to enum/bitfield variable sets
        r = config.rename_map.get
        for edef in config.enums:
            edef.variables = {r(v, v) for v in edef.variables}
        for bdef in config.bitfields:
            bdef.variables = {r(v, v) for v in bdef.variables}

    var_infos, data_files = _analyze_variables(program, config)
    var_proc_map = _find_var_proc_map(program)
    # Single-procedure vars can be inlined as locals
    single_proc_vars = {n for n, procs in var_proc_map.items()
                        if len(procs) == 1
                        and n in var_infos and var_infos[n].is_read
                        and not var_infos[n].is_const}
    demotable = _find_demotable_vars(program) | single_proc_vars

    w = _Writer()

    # --- File header ---
    w.line(f'"""Transpiled from: {source_name}"""')
    w.line()
    w.line('import time')
    has_typed = config.enums or config.bitfields
    if has_typed:
        w.line('import enum')
    w.line('from pathlib import Path')
    w.line()
    w.line('import click')
    w.line()
    w.line('from crobe.bitstring import BitString')
    w.line('from crobe.stapl.interpreter import BitArray')
    w.line()
    w.line()
    w.line('class _StaplExit(Exception):')
    w.line('    """Raised by EXIT statements to terminate execution."""')
    w.line('    def __init__(self, code):')
    w.line('        self.code = code')
    w.line('        super().__init__(f"EXIT {code}")')
    w.line()
    w.line()

    # --- Enum / bitfield classes ---
    for edef in config.enums:
        w.line(f'class {edef.class_name}(enum.IntEnum):')
        w.indent()
        for val in sorted(edef.values.keys()):
            w.line(f'{edef.values[val]} = {val}')
        w.dedent()
        w.line()
        w.line()

    for bdef in config.bitfields:
        w.line(f'class {bdef.class_name}(enum.IntFlag):')
        w.indent()
        for val in sorted(bdef.values.keys()):
            name = bdef.values[val]
            w.line(f'{name} = 0x{val:X}' if val > 255 else f'{name} = {val}')
        w.dedent()
        w.line()
        w.line()

    # --- Notes ---
    _emit_notes(w, program)

    # --- Class definition ---
    w.line('class TranspiledProgram:')
    w.indent()
    w.line(f'"""Transpiled from: {source_name}')
    w.line()
    if program.actions:
        w.line('Actions:')
        for name, action in program.actions.items():
            desc = f'  {action.description}' if action.description else ''
            w.line(f'    {name}{desc}')
    w.line('"""')
    w.line()
    w.line('DATA_DIR = Path(__file__).parent / "data"')
    w.line()

    # --- Constants (DATA int vars, never reassigned) ---
    constants = [(vi.name, vi.const_value, vi.is_array)
                 for vi in var_infos.values() if vi.is_const]
    if constants:
        def _fmt_int(v):
            return f'0x{v:X}' if isinstance(v, int) and abs(v) > 255 else str(v)
        for name, val, is_array in sorted(constants):
            if is_array:
                vals_str = ', '.join(_fmt_int(v) for v in val)
                w.line(f'{name} = [{vals_str}]')
            else:
                w.line(f'{name} = {_fmt_int(val)}')
        w.line()

    # --- Constructor (includes DATA block init) ---
    _emit_constructor(w, program, var_infos, config, demotable)

    # --- JTAG helpers ---
    _emit_helpers(w)

    # --- Procedures ---
    for proc_name, proc in program.procedures.items():
        _emit_procedure(w, proc, program, var_infos, config,
                        demotable, var_proc_map)

    # --- Actions ---
    for action_name, action in program.actions.items():
        _emit_action(w, action)

    w.dedent()  # end class
    w.line()
    w.line()

    # --- CLI ---
    _emit_cli(w, program)

    return w.text(), data_files


def _emit_notes(w, program):
    """Emit NOTE metadata as module-level comments."""
    if program.notes:
        for note in program.notes:
            w.line(f'# NOTE {note.key}: {note.value}')
        w.line()
        w.line()


def _emit_constructor(w, program, var_infos, config, demotable):
    w.line('def __init__(self, interface):')
    w.indent()
    w.line('self._iface = interface')
    w.line('self._ir_value = 0')
    w.line('self._ir_length = 0')
    w.line('self._stack = []')
    w.line('self._dr_stop = "IDLE"')
    w.line('self._ir_stop = "IDLE"')
    w.line('self._pre_dr = (0, None)')
    w.line('self._post_dr = (0, None)')
    w.line('self._pre_ir = (0, None)')
    w.line('self._post_ir = (0, None)')
    w.line('self._did_operation = False')

    # Initialize DATA block variables
    skip_vars = {n for n, vi in var_infos.items()
                 if not vi.is_read or vi.is_const} | demotable
    expr_em = _ExprEmitter(var_infos, set(), config)
    for data_block in program.data_blocks.values():
        for stmt in data_block.statements:
            match stmt:
                case IntegerDecl(name=n) | BooleanDecl(name=n) if n in skip_vars:
                    pass
                case IntegerDecl(name=n, size=sz, init=init):
                    th = expr_em._type_for_var(n)
                    if sz is not None:
                        if init is not None:
                            vals = ', '.join(expr_em.int_expr(v, _type_hint=th)
                                             for v in reversed(init))
                            w.line(f'self.{n} = [{vals}]')
                        else:
                            w.line(f'self.{n} = [0] * {expr_em.int_expr(sz)}')
                    else:
                        if init is not None:
                            w.line(f'self.{n} = {expr_em.int_expr(init[0], _type_hint=th)}')
                        else:
                            w.line(f'self.{n} = 0')
                case BooleanDecl(name=n, size=sz, init=init):
                    vi = var_infos.get(n)
                    if sz is not None:
                        if (init is not None
                                and isinstance(init, BooleanLiteral)
                                and vi and vi.extern_filename is not None):
                            w.line(f'self.{n} = BitArray({init.bit_count}, '
                                   f'(self.DATA_DIR / '
                                   f'"{vi.extern_filename}").read_bytes())')
                        elif (init is not None
                                and isinstance(init, BooleanLiteral)):
                            w.line(f'self.{n} = BitArray({init.bit_count}, '
                                   f'{init.data!r})')
                        else:
                            w.line(f'self.{n} = BitArray('
                                   f'{expr_em.int_expr(sz)})')
                    else:
                        if init is not None:
                            w.line(f'self.{n} = {expr_em.int_expr(init)}')
                        else:
                            w.line(f'self.{n} = 0')

    w.dedent()
    w.line()


def _emit_helpers(w):
    w.line('def _ir_scan(self, value, length):')
    w.indent()
    w.line('"""Shift IR register via JTAG interface directly."""')
    w.line('self._did_operation = True')
    w.line('self._ir_value = value')
    w.line('self._ir_length = length')
    w.line('tdi = BitString(value.to_bytes((length + 7) // 8, "little"), length)')
    w.line('iface = self._iface')
    w.line('iface.capture_ir()')
    w.line('iface.shift(tdi, read_tdo=False)')
    w.line('iface.run(0)')
    # (no IR cache to invalidate — we use the interface directly)
    w.dedent()
    w.line()

    w.line('def _dr_scan(self, tdi, length, capture=False):')
    w.indent()
    w.line('"""Shift DR via JTAG interface directly. Returns bytes if capture."""')
    w.line('self._did_operation = True')
    w.line('tdi_bs = BitString(bytes(tdi), length)')
    w.line('iface = self._iface')
    w.line('iface.capture_dr()')
    w.line('result = iface.shift(tdi_bs, read_tdo=capture)')
    w.line('iface.run(0)')
    w.line('if capture:')
    w.indent()
    w.line('return bytes(result.data[:((length + 7) // 8)])')
    w.dedent()
    w.line('return None')
    w.dedent()
    w.line()

    w.line('def _state(self, *states):')
    w.indent()
    w.line('"""Transition TAP through states."""')
    w.line('for state in states:')
    w.indent()
    w.line("if state == 'RESET':")
    w.indent()
    w.line('self._trst(None, None)')
    w.dedent()
    w.line('else:')
    w.indent()
    w.line('self._iface.run(1)')
    w.dedent()
    w.dedent()
    w.dedent()
    w.line()

    w.line('def _wait(self, wait_state, cycles, usecs, end_state):')
    w.indent()
    w.line('"""Wait with optional state transitions and delay."""')
    w.line('if wait_state:')
    w.indent()
    w.line('self._state(wait_state)')
    w.dedent()
    w.line('if cycles:')
    w.indent()
    w.line('self._iface.run(cycles)')
    w.dedent()
    w.line('if usecs:')
    w.indent()
    w.line('time.sleep(usecs / 1_000_000)')
    w.dedent()
    w.line('if end_state and end_state != wait_state:')
    w.indent()
    w.line('self._state(end_state)')
    w.dedent()
    w.dedent()
    w.line()

    w.line('def _trst(self, cycles, usecs):')
    w.indent()
    w.line('"""TAP reset via TMS sequence.')
    w.line()
    w.line('Warning: TRST after other operations may invalidate chain')
    w.line('state, requiring full re-enumeration.')
    w.line('"""')
    w.line('if self._did_operation:')
    w.indent()
    w.line("import logging")
    w.line("logging.getLogger(__name__).warning(")
    w.line("    'TRST after operations: chain state may need re-enumeration')")
    w.dedent()
    w.line('self._did_operation = True')
    w.line('# 5 TMS=1 clocks guarantees reset from any state')
    w.line('self._iface.run(1)')
    w.dedent()
    w.line()

    w.line('def _frequency(self, hertz):')
    w.indent()
    w.line('"""Set TCK frequency (no-op without adapter access)."""')
    w.line('pass')
    w.dedent()
    w.line()

    w.line('def _export(self, key, value):')
    w.indent()
    w.line('"""Export a key/value pair."""')
    w.line('print(f"EXPORT {key} = {value}")')
    w.dedent()
    w.line()


def _emit_procedure(w, proc, program, var_infos, config,
                    demotable=set(), var_proc_map=None):
    """Emit a procedure as a sync method."""
    proc_data_vars = _collect_data_vars(proc, program)
    # Only demote vars that are actually referenced in this procedure
    if var_proc_map is not None:
        proc_demotable = {n for n in demotable
                          if proc.name in var_proc_map.get(n, set())}
    else:
        proc_demotable = demotable
    const_names = {n for n, vi in var_infos.items() if vi.is_const}
    proc_locals = _collect_proc_locals(proc) | (
        proc_data_vars & proc_demotable - const_names)
    data_vars = proc_data_vars

    w.line(f'def _proc_{proc.name.lower()}(self):')
    w.indent()
    w.line(f'"""PROCEDURE {proc.name}"""')

    # Emit inline init for demoted DATA vars referenced in this procedure
    inlined = proc_data_vars & proc_demotable - const_names
    if inlined:
        expr_em = _ExprEmitter(var_infos, proc_locals, config)
        for data_name in proc.uses:
            db = program.data_blocks.get(data_name)
            if not db:
                continue
            for stmt in db.statements:
                match stmt:
                    case IntegerDecl(name=n) if n in inlined:
                        if stmt.size is not None:
                            if stmt.init is not None:
                                vals = ', '.join(expr_em.int_expr(v)
                                                 for v in reversed(stmt.init))
                                w.line(f'{n} = [{vals}]')
                            else:
                                w.line(f'{n} = [0] * {expr_em.int_expr(stmt.size)}')
                        else:
                            if stmt.init is not None:
                                w.line(f'{n} = {expr_em.int_expr(stmt.init[0])}')
                            else:
                                w.line(f'{n} = 0')
                    case BooleanDecl(name=n) if n in inlined:
                        vi = var_infos.get(n)
                        if stmt.size is not None:
                            if (stmt.init is not None
                                    and isinstance(stmt.init, BooleanLiteral)
                                    and vi and vi.extern_filename is not None):
                                w.line(f'{n} = BitArray({stmt.init.bit_count}, '
                                       f'(self.DATA_DIR / "{vi.extern_filename}").read_bytes())')
                            elif (stmt.init is not None
                                    and isinstance(stmt.init, BooleanLiteral)):
                                w.line(f'{n} = BitArray({stmt.init.bit_count}, '
                                       f'{stmt.init.data!r})')
                            else:
                                w.line(f'{n} = BitArray({expr_em.int_expr(stmt.size)})')
                        else:
                            if stmt.init is not None:
                                w.line(f'{n} = {expr_em.int_expr(stmt.init)}')
                            else:
                                w.line(f'{n} = 0')

    # Build control flow
    stmts = proc.statements
    labels = proc.labels

    # Preprocess FOR/NEXT
    try:
        processed, adjusted_labels = _preprocess_for_next(stmts, labels)
    except AssertionError:
        # Labels inside FOR/NEXT: fall back to flat emission
        processed = stmts
        adjusted_labels = labels

    # Build basic blocks
    blocks, name_to_idx = _build_blocks(processed, adjusted_labels)

    # Recover control flow
    structured = _recover_control_flow(blocks, name_to_idx)

    # Emit
    expr_em = _ExprEmitter(var_infos, proc_locals, config)
    stmt_em = _StmtEmitter(w, expr_em, var_infos, proc_locals, program)
    stmt_em.emit_structured(structured)

    # Ensure method body is not empty
    if not structured:
        w.line('pass')

    w.dedent()
    w.line()


def _emit_action(w, action):
    """Emit an action as a sync method."""
    desc = f': {action.description}' if action.description else ''
    w.line(f'def action_{action.name.lower()}(self):')
    w.indent()
    w.line(f'"""ACTION {action.name}{desc}"""')
    w.line('try:')
    w.indent()
    for proc_name, modifier in action.procedures:
        if modifier == 'OPTIONAL':
            w.line(f'# OPTIONAL: self._proc_{proc_name.lower()}()')
        elif modifier == 'RECOMMENDED':
            w.line(f'self._proc_{proc_name.lower()}()  # RECOMMENDED')
        else:
            w.line(f'self._proc_{proc_name.lower()}()')
    w.line('return 0')
    w.dedent()
    w.line('except _StaplExit as e:')
    w.indent()
    w.line('return e.code')
    w.dedent()
    w.dedent()
    w.line()


def _emit_cli(w, program):
    """Emit click CLI entry point (sync, crobe-style)."""
    # Collect action names for help text
    action_names = list(program.actions.keys())
    action_help = ', '.join(action_names) if action_names else 'none'

    w.line('@click.command()')
    w.line("@click.option('-r', '--root', 'root_path', required=True,")
    w.line("              help='crobe root path to a JTAG Interface')")
    w.line("@click.option('-a', '--action', 'action_name', default=None,")
    w.line(f"              help='Action to execute (available: {action_help})')")
    w.line('def main(root_path, action_name):')
    w.indent()
    w.line('"""Execute transpiled STAPL program."""')
    w.line('from crobe.root import root as _resolve_root')
    w.line('from crobe.protocol.jtag import Interface')
    w.line()
    w.line('node = _resolve_root(root_path)')
    w.line('if not isinstance(node, Interface):')
    w.indent()
    w.line("click.echo(f'Root {root_path} resolved to {type(node).__name__}, expected a JTAG Interface.', err=True)")
    w.line('raise SystemExit(1)')
    w.dedent()
    w.line('interface = node')
    w.line()
    w.line('prog = TranspiledProgram(interface)')
    w.line()
    w.line('if action_name is None:')
    w.indent()
    if action_names:
        w.line(f'action_name = {action_names[0]!r}')
    else:
        w.line("click.echo('No actions available.', err=True)")
        w.line('raise SystemExit(1)')
    w.dedent()
    w.line()
    w.line("action_method = getattr(prog, f'action_{action_name.lower()}', None)")
    w.line('if action_method is None:')
    w.indent()
    w.line("click.echo(f'Unknown action: {action_name}', err=True)")
    w.line('raise SystemExit(1)')
    w.dedent()
    w.line()
    w.line('exit_code = action_method()')
    w.line('if exit_code:')
    w.indent()
    w.line("click.echo(f'Action {action_name} failed with exit code {exit_code}', err=True)")
    w.line('raise SystemExit(exit_code)')
    w.dedent()
    w.line("click.echo(f'Action {action_name} completed successfully.')")
    w.dedent()
    w.line()
    w.line()
    w.line("if __name__ == '__main__':")
    w.indent()
    w.line('main()')
    w.dedent()
