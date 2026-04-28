"""STAPL (JESD71) interpreter.

Executes a parsed STAPL Program by evaluating expressions, managing
variables, and dispatching JTAG operations to a pluggable Player.
"""

import math
from dataclasses import dataclass

from .parser import (
    Program, ProcedureDef, DataBlock,
    Expr, IntLiteral, VarRef, ArrayIndex, ArraySubrange, ArrayWhole,
    UnaryOp, BinOp, FuncCall, BooleanLiteral,
    IntegerDecl, BooleanDecl,
    AssignStmt, GotoStmt, CallStmt, ExitStmt, IfStmt,
    ForStmt, NextStmt, PushStmt, PopStmt,
    DrScanStmt, IrScanStmt, DrStopStmt, IrStopStmt,
    StateStmt, WaitStmt, TrstStmt, FrequencyStmt,
    PreDrStmt, PostDrStmt, PreIrStmt, PostIrStmt,
    PrintStmt, ExportStmt, VmapStmt, VectorStmt,
)
from .lexer import StaplError


class StaplRuntimeError(StaplError):
    pass


class StaplExit(Exception):
    """Raised when EXIT statement is executed."""
    def __init__(self, code: int):
        self.code = code
        super().__init__(f"EXIT {code}")


# --- Bit array (Boolean) storage ---

class BitArray:
    """Mutable bit array, stored LSB-first in a bytearray."""
    __slots__ = ('_data', '_size')

    def __init__(self, size: int, data: bytes | None = None):
        self._size = int(size)
        byte_count = (self._size + 7) // 8
        if data is not None:
            self._data = bytearray(data[:byte_count])
            if len(self._data) < byte_count:
                self._data.extend(b'\x00' * (byte_count - len(self._data)))
        else:
            self._data = bytearray(byte_count)

    @property
    def size(self):
        return self._size

    def __getitem__(self, key):
        if isinstance(key, slice):
            start, stop, step = key.start, key.stop, key.step
            if step is None or step == 1:
                # a[start:stop] → ascending, exclusive end
                size = stop - start
                result = BitArray(size)
                for i in range(size):
                    result.set_bit(i, self.get_bit(start + i))
                return result
            elif step == -1:
                # a[start:stop:-1] → descending, exclusive end
                # stop=None means go down to index 0 inclusive
                end = stop if stop is not None else -1
                size = start - end
                result = BitArray(size)
                for i in range(size):
                    result.set_bit(i, self.get_bit(start - i))
                return result
            else:
                assert False, f"unsupported step {step}"
        return self.get_bit(key)

    def __setitem__(self, key, value):
        if isinstance(key, slice):
            start, stop, step = key.start, key.stop, key.step
            if step is None or step == 1:
                size = stop - start
                for i in range(min(size, value.size)):
                    self.set_bit(start + i, value.get_bit(i))
            elif step == -1:
                end = stop if stop is not None else -1
                size = start - end
                for i in range(min(size, value.size)):
                    self.set_bit(start - i, value.get_bit(i))
            else:
                assert False, f"unsupported step {step}"
        else:
            self.set_bit(key, value)

    def get_bit(self, index: int) -> int:
        if index < 0 or index >= self._size:
            return 0
        return (self._data[index >> 3] >> (index & 7)) & 1

    def set_bit(self, index: int, value: int):
        if index < 0 or index >= self._size:
            return
        byte_idx = index >> 3
        bit_idx = index & 7
        if value:
            self._data[byte_idx] |= (1 << bit_idx)
        else:
            self._data[byte_idx] &= ~(1 << bit_idx)

    def get_subrange(self, high: int, low: int) -> 'BitArray':
        """Extract bits [low..high] into a new BitArray (STAPL convention)."""
        if high >= low:
            return self[low:high + 1]
        else:
            stop = high - 1 if high > 0 else None
            return self[low:stop:-1]

    def set_subrange(self, high: int, low: int, source: 'BitArray'):
        """Set bits [low..high] from source BitArray (STAPL convention)."""
        if high >= low:
            self[low:high + 1] = source
        else:
            stop = high - 1 if high > 0 else None
            self[low:stop:-1] = source

    def to_bytes(self) -> bytes:
        return bytes(self._data)

    def to_int(self) -> int:
        """Convert to unsigned integer (up to 32 bits)."""
        val = 0
        for i in range(min(self._size, 32)):
            val |= self.get_bit(i) << i
        return val

    @classmethod
    def from_int(cls, value: int, size: int = 32) -> 'BitArray':
        """Create BitArray from integer value."""
        result = cls(size)
        for i in range(size):
            if value & (1 << i):
                result.set_bit(i, 1)
        return result

    def compare(self, other: 'BitArray', mask: 'BitArray', length: int) -> bool:
        """Compare self against other, using mask to select which bits to compare."""
        for i in range(length):
            if i < mask.size and mask.get_bit(i):
                a = self.get_bit(i) if i < self.size else 0
                b = other.get_bit(i) if i < other.size else 0
                if a != b:
                    return False
        return True


# --- Player protocol ---

class StaplPlayer:
    """Abstract player protocol. Override for actual hardware interaction."""

    def ir_scan(self, length: int, tdi: bytes,
                pre: tuple[int, bytes], post: tuple[int, bytes],
                capture: bool) -> bytes | None:
        assert False, "ir_scan not implemented"

    def dr_scan(self, length: int, tdi: bytes,
                pre: tuple[int, bytes], post: tuple[int, bytes],
                capture: bool) -> bytes | None:
        assert False, "dr_scan not implemented"

    def state(self, target: str, path: list[str] | None = None):
        assert False, "state not implemented"

    def wait(self, wait_state: str | None, cycles: int | None,
             usecs: int | None, end_state: str | None):
        assert False, "wait not implemented"

    def trst(self, cycles: int | None, usecs: int | None):
        assert False, "trst not implemented"

    def frequency(self, hertz: int | None):
        pass  # optional

    def note(self, text: str):
        pass

    def export(self, key: str, value):
        pass

    def vector(self, dir_vec: bytes, in_vec: bytes,
               capture: bool) -> bytes | None:
        assert False, "vector not implemented"


# --- Interpreter ---

@dataclass
class _ForState:
    var: str
    end: int
    step: int
    pc: int  # statement index of the FOR statement


class Interpreter:
    """STAPL program interpreter."""

    def __init__(self, program: Program):
        self._program = program
        self._integers: dict[str, int | list[int]] = {}
        self._booleans: dict[str, BitArray] = {}
        self._bool_scalars: set[str] = set()  # names of scalar booleans
        self._stack: list[int] = []
        self._call_stack: list[tuple[str, int]] = []  # (proc_name, pc)
        self._for_stack: list[_ForState] = []
        self._pre_dr: tuple[int, bytes] = (0, b'')
        self._post_dr: tuple[int, bytes] = (0, b'')
        self._pre_ir: tuple[int, bytes] = (0, b'')
        self._post_ir: tuple[int, bytes] = (0, b'')
        self._dr_stop: str = 'IDLE'
        self._ir_stop: str = 'IDLE'
        self._initialized_data: set[str] = set()
        self._vmap_signals: list[str] = []

    def execute(self, action_name: str, player: StaplPlayer,
                *, include: set[str] | None = None,
                exclude: set[str] | None = None):
        """Execute a STAPL action.

        Args:
            action_name: Name of the ACTION to execute.
            player: Player instance for hardware operations.
            include: Optional set of OPTIONAL procedures to include.
            exclude: Optional set of RECOMMENDED procedures to exclude.
        """
        action_name = action_name.upper()
        if action_name not in self._program.actions:
            raise StaplRuntimeError(f"Action not found: {action_name}")

        action = self._program.actions[action_name]
        include = include or set()
        exclude = exclude or set()

        # Build procedure call list
        procs_to_call = []
        for proc_name, modifier in action.procedures:
            if modifier == 'OPTIONAL' and proc_name.upper() not in include:
                continue
            if modifier == 'RECOMMENDED' and proc_name.upper() in exclude:
                continue
            procs_to_call.append(proc_name.upper())

        try:
            for proc_name in procs_to_call:
                self._execute_procedure(proc_name, player)
        except StaplExit as e:
            return e.code

        return 0

    def _execute_procedure(self, proc_name: str, player: StaplPlayer):
        """Execute a PROCEDURE block."""
        proc_name = proc_name.upper()
        if proc_name not in self._program.procedures:
            raise StaplRuntimeError(f"Procedure not found: {proc_name}")

        proc = self._program.procedures[proc_name]

        # Initialize DATA blocks referenced by USES
        for dep_name in proc.uses:
            dep_upper = dep_name.upper()
            if dep_upper in self._program.data_blocks:
                self._init_data_block(dep_upper)
            # If it's another procedure, that's fine — USES can reference both

        pc = 0
        while pc < len(proc.statements):
            stmt = proc.statements[pc]
            pc = self._execute_stmt(stmt, pc, proc, player)

    def _execute_stmt(self, stmt, pc: int, proc: ProcedureDef,
                      player: StaplPlayer) -> int:
        """Execute one statement. Returns next pc."""
        match stmt:
            case IntegerDecl():
                self._exec_integer_decl(stmt)
            case BooleanDecl():
                self._exec_boolean_decl(stmt)
            case AssignStmt():
                self._exec_assign(stmt)
            case GotoStmt():
                label = stmt.label.upper()
                if label not in proc.labels:
                    raise StaplRuntimeError(f"Label not found: {label}")
                return proc.labels[label]
            case CallStmt():
                self._call_stack.append((proc.name, pc + 1))
                self._execute_procedure(stmt.procedure.upper(), player)
                return pc + 1
            case ExitStmt():
                code = self._eval_int(stmt.code)
                raise StaplExit(code)
            case IfStmt():
                cond = self._eval_int(stmt.condition)
                if cond:
                    return self._execute_stmt(stmt.then_stmt, pc, proc, player)
                return pc + 1
            case ForStmt():
                start = self._eval_int(stmt.start)
                end = self._eval_int(stmt.end)
                step = self._eval_int(stmt.step) if stmt.step else 1
                self._integers[stmt.var] = start
                self._for_stack.append(_ForState(
                    var=stmt.var, end=end, step=step, pc=pc + 1))
            case NextStmt():
                return self._exec_next(stmt, pc, proc)
            case PushStmt():
                self._stack.append(self._eval_int(stmt.value))
            case PopStmt():
                if not self._stack:
                    raise StaplRuntimeError("POP on empty stack")
                val = self._stack.pop()
                if stmt.index is not None:
                    idx = self._eval_int(stmt.index)
                    arr = self._integers[stmt.target]
                    assert isinstance(arr, list)
                    arr[idx] = val
                elif stmt.target in self._bool_scalars:
                    assert val in (0, 1), f"POP to boolean: value must be 0 or 1, got {val}"
                    ba = self._booleans[stmt.target]
                    ba.set_bit(0, val)
                else:
                    self._integers[stmt.target] = val
            case DrScanStmt():
                self._exec_scan(stmt, player, is_ir=False)
            case IrScanStmt():
                self._exec_scan(stmt, player, is_ir=True)
            case DrStopStmt():
                self._dr_stop = stmt.state
            case IrStopStmt():
                self._ir_stop = stmt.state
            case StateStmt():
                path = stmt.path
                player.state(path[-1], path[:-1] if len(path) > 1 else None)
            case WaitStmt():
                cycles = self._eval_int(stmt.cycles) if stmt.cycles else None
                usecs = self._eval_int(stmt.usecs) if stmt.usecs else None
                player.wait(stmt.wait_state, cycles, usecs, stmt.end_state)
            case TrstStmt():
                cycles = self._eval_int(stmt.cycles) if stmt.cycles else None
                usecs = self._eval_int(stmt.usecs) if stmt.usecs else None
                player.trst(cycles, usecs)
            case FrequencyStmt():
                hz = self._eval_int(stmt.value) if stmt.value else None
                player.frequency(hz)
            case PreDrStmt():
                count = self._eval_int(stmt.count)
                data = self._eval_bits(stmt.data).to_bytes() if stmt.data else _ones_bytes(count)
                self._pre_dr = (count, data)
            case PostDrStmt():
                count = self._eval_int(stmt.count)
                data = self._eval_bits(stmt.data).to_bytes() if stmt.data else _ones_bytes(count)
                self._post_dr = (count, data)
            case PreIrStmt():
                count = self._eval_int(stmt.count)
                data = self._eval_bits(stmt.data).to_bytes() if stmt.data else _ones_bytes(count)
                self._pre_ir = (count, data)
            case PostIrStmt():
                count = self._eval_int(stmt.count)
                data = self._eval_bits(stmt.data).to_bytes() if stmt.data else _ones_bytes(count)
                self._post_ir = (count, data)
            case PrintStmt():
                text = self._eval_print(stmt)
                player.note(text)
            case ExportStmt():
                value = self._eval_export_value(stmt.value)
                player.export(stmt.key, value)
            case VmapStmt():
                self._vmap_signals = stmt.signals
            case VectorStmt():
                self._exec_vector(stmt, player)
            case _:
                raise StaplRuntimeError(f"Unhandled statement type: {type(stmt).__name__}")

        return pc + 1

    # --- Variable initialization ---

    def _exec_integer_decl(self, decl: IntegerDecl):
        if decl.size is not None:
            size = self._eval_int(decl.size)
            if decl.init:
                # Altera's JAM player stores INTEGER array init values
                # in reverse order: last listed value → index 0.
                # JESD71 is ambiguous about this, but Quartus-generated
                # STAPL files depend on this behavior.
                vals = [self._eval_int(v) for v in decl.init]
                vals.reverse()
                while len(vals) < size:
                    vals.append(0)
                self._integers[decl.name] = vals
            else:
                self._integers[decl.name] = [0] * size
        else:
            if decl.init:
                self._integers[decl.name] = self._eval_int(decl.init[0])
            else:
                self._integers[decl.name] = 0

    def _exec_boolean_decl(self, decl: BooleanDecl):
        if decl.size is not None:
            size = self._eval_int(decl.size)
            if decl.init and isinstance(decl.init, BooleanLiteral):
                self._booleans[decl.name] = BitArray(size, decl.init.data)
            else:
                self._booleans[decl.name] = BitArray(size)
        else:
            # Scalar boolean
            self._bool_scalars.add(decl.name)
            if decl.init:
                val = self._eval_int(decl.init)
                ba = BitArray(1)
                ba.set_bit(0, val)
                self._booleans[decl.name] = ba
            else:
                self._booleans[decl.name] = BitArray(1)

    def _init_data_block(self, name: str):
        if name in self._initialized_data:
            return
        self._initialized_data.add(name)
        block = self._program.data_blocks[name]
        for stmt in block.statements:
            if isinstance(stmt, IntegerDecl):
                self._exec_integer_decl(stmt)
            elif isinstance(stmt, BooleanDecl):
                self._exec_boolean_decl(stmt)

    # --- Assignment ---

    def _exec_assign(self, stmt: AssignStmt):
        name = stmt.target

        if stmt.high is not None and stmt.low is not None:
            # Subrange assignment
            high = self._eval_int(stmt.high)
            low = self._eval_int(stmt.low)
            source = self._eval_bits(stmt.value)
            self._booleans[name].set_subrange(high, low, source)
        elif stmt.index is not None:
            idx = self._eval_int(stmt.index)
            if name in self._integers:
                val = self._integers[name]
                if isinstance(val, list):
                    val[idx] = self._eval_int(stmt.value)
                else:
                    raise StaplRuntimeError(f"Cannot index scalar integer {name}")
            elif name in self._booleans:
                bit_val = self._eval_int(stmt.value)
                self._booleans[name].set_bit(idx, bit_val)
            else:
                raise StaplRuntimeError(f"Undefined variable: {name}")
        else:
            # Whole assignment
            if name in self._booleans and name not in self._bool_scalars:
                # Array assignment
                source = self._eval_bits(stmt.value)
                target = self._booleans[name]
                # Copy all bits
                for i in range(min(source.size, target.size)):
                    target.set_bit(i, source.get_bit(i))
            elif name in self._bool_scalars:
                val = self._eval_int(stmt.value)
                self._booleans[name].set_bit(0, val)
            elif name in self._integers:
                val = self._integers[name]
                if isinstance(val, list):
                    # Whole array assignment from another array
                    source_val = self._eval_int(stmt.value)
                    raise StaplRuntimeError("Cannot assign scalar to integer array")
                else:
                    self._integers[name] = self._eval_int(stmt.value)
            else:
                raise StaplRuntimeError(f"Undefined variable: {name}")

    # --- FOR/NEXT ---

    def _exec_next(self, stmt: NextStmt, pc: int, proc: ProcedureDef) -> int:
        var_name = stmt.var
        if not self._for_stack:
            raise StaplRuntimeError(f"NEXT {var_name} without matching FOR")

        for_state = self._for_stack[-1]
        if for_state.var != var_name:
            raise StaplRuntimeError(
                f"NEXT {var_name} doesn't match FOR {for_state.var}")

        current = self._integers[var_name]
        assert isinstance(current, int)
        new_val = current + for_state.step

        # Check termination
        if for_state.step > 0:
            done = new_val > for_state.end
        elif for_state.step < 0:
            done = new_val < for_state.end
        else:
            # STEP 0: only the initial check matters
            done = True

        if done:
            self._for_stack.pop()
            return pc + 1
        else:
            self._integers[var_name] = new_val
            return for_state.pc

    # --- SCAN operations ---

    def _exec_scan(self, stmt, player: StaplPlayer, *, is_ir: bool):
        length = self._eval_int(stmt.length)
        tdi = self._eval_bits(stmt.tdi)
        needs_capture = stmt.capture is not None or stmt.compare is not None

        if is_ir:
            pre = self._pre_ir
            post = self._post_ir
        else:
            pre = self._pre_dr
            post = self._post_dr

        if is_ir:
            tdo_bytes = player.ir_scan(length, tdi.to_bytes(),
                                       pre=pre, post=post,
                                       capture=needs_capture)
        else:
            tdo_bytes = player.dr_scan(length, tdi.to_bytes(),
                                       pre=pre, post=post,
                                       capture=needs_capture)

        if stmt.capture is not None and tdo_bytes is not None:
            tdo = BitArray(length, tdo_bytes)
            self._store_bits(stmt.capture, tdo)

        if stmt.compare is not None and tdo_bytes is not None:
            tdo = BitArray(length, tdo_bytes)
            expected = self._eval_bits(stmt.compare)
            mask = self._eval_bits(stmt.mask) if stmt.mask else BitArray(length, _ones_bytes(length))
            match = tdo.compare(expected, mask, length)
            if stmt.result is not None:
                self._store_bool_result(stmt.result, 1 if match else 0)

    # --- VECTOR ---

    def _exec_vector(self, stmt: VectorStmt, player: StaplPlayer):
        dir_vec = self._eval_bits(stmt.dir_vec)
        in_vec = self._eval_bits(stmt.in_vec)
        needs_capture = stmt.capture is not None or stmt.compare is not None

        tdo_bytes = player.vector(dir_vec.to_bytes(), in_vec.to_bytes(),
                                  capture=needs_capture)

        if stmt.capture is not None and tdo_bytes is not None:
            tdo = BitArray(dir_vec.size, tdo_bytes)
            self._store_bits(stmt.capture, tdo)

        if stmt.compare is not None and tdo_bytes is not None:
            tdo = BitArray(dir_vec.size, tdo_bytes)
            expected = self._eval_bits(stmt.compare)
            mask_bits = self._eval_bits(stmt.mask) if stmt.mask else BitArray(dir_vec.size, _ones_bytes(dir_vec.size))
            match = tdo.compare(expected, mask_bits, dir_vec.size)
            if stmt.result is not None:
                self._store_bool_result(stmt.result, 1 if match else 0)

    # --- Expression evaluation ---

    def _eval_int(self, expr: Expr) -> int:
        """Evaluate an expression as a 32-bit signed integer."""
        match expr:
            case IntLiteral(value=v):
                return v
            case VarRef(name=name):
                if name in self._integers:
                    val = self._integers[name]
                    assert isinstance(val, int), f"{name} is an array, not scalar"
                    return val
                if name in self._booleans:
                    ba = self._booleans[name]
                    if name in self._bool_scalars:
                        return ba.get_bit(0)
                    return ba.to_int()
                raise StaplRuntimeError(f"Undefined variable: {name}")
            case ArrayIndex(name=name, index=idx_expr):
                idx = self._eval_int(idx_expr)
                if name in self._integers:
                    arr = self._integers[name]
                    assert isinstance(arr, list)
                    if idx < 0 or idx >= len(arr):
                        return 0
                    return arr[idx]
                if name in self._booleans:
                    return self._booleans[name].get_bit(idx)
                raise StaplRuntimeError(f"Undefined variable: {name}")
            case UnaryOp(op=op, operand=operand):
                val = self._eval_int(operand)
                if op == '-':
                    return -val
                elif op == '~':
                    return ~val & 0xFFFFFFFF
                elif op == '!':
                    return 0 if val else 1
                assert False, f"Unknown unary op: {op}"
            case BinOp(op=op, left=left, right=right):
                return self._eval_binop(op, left, right)
            case FuncCall(name='ABS', arg=arg):
                return abs(self._eval_int(arg))
            case FuncCall(name='INT', arg=arg):
                ba = self._eval_bits(arg)
                return ba.to_int()
            case BooleanLiteral():
                # Single-bit or small boolean used as integer
                ba = BitArray(expr.bit_count, expr.data)
                return ba.to_int()
            case _:
                raise StaplRuntimeError(f"Cannot evaluate as integer: {type(expr).__name__}")

    def _eval_binop(self, op: str, left: Expr, right: Expr) -> int:
        a = self._eval_int(left)
        b = self._eval_int(right)
        match op:
            case '+': return _to_signed32(a + b)
            case '-': return _to_signed32(a - b)
            case '*': return _to_signed32(a * b)
            case '/':
                if b == 0:
                    raise StaplRuntimeError("Division by zero")
                return _to_signed32(int(a / b))  # truncate toward zero
            case '%':
                if b == 0:
                    raise StaplRuntimeError("Modulo by zero")
                return a % b
            case '<<': return _to_signed32(a << b)
            case '>>': return _to_signed32(a >> b)
            case '&': return a & b
            case '|': return a | b
            case '^': return a ^ b
            case '==': return 1 if a == b else 0
            case '!=': return 1 if a != b else 0
            case '<': return 1 if a < b else 0
            case '>': return 1 if a > b else 0
            case '<=': return 1 if a <= b else 0
            case '>=': return 1 if a >= b else 0
            case '&&': return 1 if (a and b) else 0
            case '||': return 1 if (a or b) else 0
            case _:
                assert False, f"Unknown binary op: {op}"

    def _eval_bits(self, expr: Expr) -> BitArray:
        """Evaluate an expression as a BitArray."""
        match expr:
            case BooleanLiteral(data=data, bit_count=bc):
                return BitArray(bc, data)
            case VarRef(name=name):
                if name in self._booleans:
                    return self._booleans[name]
                if name in self._integers:
                    val = self._integers[name]
                    assert isinstance(val, int)
                    return BitArray.from_int(val)
                raise StaplRuntimeError(f"Undefined variable: {name}")
            case ArraySubrange(name=name, high=high_expr, low=low_expr):
                high = self._eval_int(high_expr)
                low = self._eval_int(low_expr)
                if name in self._booleans:
                    return self._booleans[name].get_subrange(high, low)
                raise StaplRuntimeError(f"Subrange on non-boolean: {name}")
            case ArrayWhole(name=name):
                if name in self._booleans:
                    return self._booleans[name]
                raise StaplRuntimeError(f"Whole array ref on non-boolean: {name}")
            case FuncCall(name='BOOL', arg=arg):
                val = self._eval_int(arg)
                return BitArray.from_int(val)
            case _:
                # Fall back to integer evaluation and convert
                val = self._eval_int(expr)
                return BitArray.from_int(val)

    def _store_bits(self, target_expr: Expr, source: BitArray):
        """Store a BitArray result into a target expression."""
        match target_expr:
            case VarRef(name=name):
                if name in self._booleans:
                    target = self._booleans[name]
                    for i in range(min(source.size, target.size)):
                        target.set_bit(i, source.get_bit(i))
                else:
                    raise StaplRuntimeError(f"Cannot store bits to {name}")
            case ArraySubrange(name=name, high=h, low=l):
                high = self._eval_int(h)
                low = self._eval_int(l)
                self._booleans[name].set_subrange(high, low, source)
            case ArrayWhole(name=name):
                target = self._booleans[name]
                for i in range(min(source.size, target.size)):
                    target.set_bit(i, source.get_bit(i))
            case _:
                raise StaplRuntimeError(f"Invalid capture target: {type(target_expr).__name__}")

    def _store_bool_result(self, target_expr: Expr, value: int):
        """Store a boolean (0/1) comparison result."""
        match target_expr:
            case VarRef(name=name):
                if name in self._bool_scalars:
                    self._booleans[name].set_bit(0, value)
                elif name in self._integers:
                    self._integers[name] = value
                else:
                    raise StaplRuntimeError(f"Cannot store result to {name}")
            case ArrayIndex(name=name, index=idx_expr):
                idx = self._eval_int(idx_expr)
                if name in self._booleans:
                    self._booleans[name].set_bit(idx, value)
                elif name in self._integers:
                    arr = self._integers[name]
                    assert isinstance(arr, list)
                    arr[idx] = value
                else:
                    raise StaplRuntimeError(f"Cannot store result to {name}[{idx}]")
            case _:
                raise StaplRuntimeError(f"Invalid result target: {type(target_expr).__name__}")

    # --- PRINT ---

    def _eval_print(self, stmt: PrintStmt) -> str:
        parts = []
        for part in stmt.parts:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, FuncCall) and part.name == 'CHR$':
                val = self._eval_int(part.arg)
                parts.append(chr(val))
            else:
                val = self._eval_int(part)
                parts.append(str(val))
        return ''.join(parts)

    def _eval_export_value(self, expr: Expr):
        """Evaluate EXPORT value — returns int or bytes."""
        try:
            return self._eval_int(expr)
        except (StaplRuntimeError, AssertionError):
            ba = self._eval_bits(expr)
            return ba.to_bytes()


# --- Utilities ---

def _to_signed32(val: int) -> int:
    """Truncate to 32-bit signed integer."""
    val &= 0xFFFFFFFF
    if val & 0x80000000:
        val -= 0x100000000
    return val


def _ones_bytes(bit_count: int) -> bytes:
    """Create bytes of all 1s for the given bit count."""
    byte_count = (bit_count + 7) // 8
    data = bytearray(b'\xFF' * byte_count)
    # Mask excess bits in last byte
    excess = bit_count & 7
    if excess:
        data[-1] = (1 << excess) - 1
    return bytes(data)
