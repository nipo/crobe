"""STAPL file inspection CLI commands."""

from pathlib import Path

import click

from . import base


@base.cli.group(help="STAPL file operations")
def stapl():
    pass


@stapl.command(help="Dump STAPL file as pseudocode")
@click.argument('filename', type=click.Path(exists=True))
@click.option('--no-crc', is_flag=True, help="Skip CRC verification")
def dump(filename, no_crc):
    from ..stapl import load
    from ..stapl.parser import (
        Program, ActionDef, ProcedureDef, DataBlock,
        IntegerDecl, BooleanDecl,
        AssignStmt, GotoStmt, CallStmt, ExitStmt, IfStmt,
        ForStmt, NextStmt, PushStmt, PopStmt,
        DrScanStmt, IrScanStmt, DrStopStmt, IrStopStmt,
        StateStmt, WaitStmt, TrstStmt, FrequencyStmt,
        PreDrStmt, PostDrStmt, PreIrStmt, PostIrStmt,
        PrintStmt, ExportStmt, VmapStmt, VectorStmt,
        Expr, IntLiteral, VarRef, ArrayIndex, ArraySubrange,
        ArrayWhole, UnaryOp, BinOp, FuncCall, BooleanLiteral,
    )

    with open(filename, 'r') as f:
        source = f.read()

    prog = load(source, check_crc=not no_crc)

    # --- Expression formatter ---

    def fmt_expr(e: Expr) -> str:
        match e:
            case IntLiteral(value=v):
                return str(v)
            case VarRef(name=n):
                return n
            case ArrayIndex(name=n, index=idx):
                return f"{n}[{fmt_expr(idx)}]"
            case ArraySubrange(name=n, high=h, low=l):
                return f"{n}[{fmt_expr(h)}..{fmt_expr(l)}]"
            case ArrayWhole(name=n):
                return f"{n}[]"
            case UnaryOp(op=op, operand=a):
                return f"{op}{fmt_expr(a)}"
            case BinOp(op=op, left=a, right=b):
                return f"({fmt_expr(a)} {op} {fmt_expr(b)})"
            case FuncCall(name=n, arg=a):
                return f"{n}({fmt_expr(a)})"
            case BooleanLiteral(bit_count=bc):
                return f"<{bc} bits>"
            case _:
                return repr(e)

    def fmt_expr_or_none(e):
        return fmt_expr(e) if e is not None else None

    # --- Statement formatter ---

    def fmt_stmt(stmt, indent=0):
        pad = "    " * indent

        match stmt:
            case IntegerDecl(name=n, size=sz, init=init):
                s = f"INTEGER {n}"
                if sz is not None:
                    s += f"[{fmt_expr(sz)}]"
                if init is not None:
                    if sz is not None:
                        s += f" = <{len(init)} values>"
                    else:
                        s += f" = {fmt_expr(init[0])}"
                click.echo(f"{pad}{s}")

            case BooleanDecl(name=n, size=sz, init=init):
                s = f"BOOLEAN {n}"
                if sz is not None:
                    s += f"[{fmt_expr(sz)}]"
                if init is not None:
                    if isinstance(init, BooleanLiteral):
                        s += f" = <{init.bit_count} bits>"
                    else:
                        s += f" = {fmt_expr(init)}"
                click.echo(f"{pad}{s}")

            case AssignStmt(target=t, index=idx, high=h, low=l, value=v):
                lhs = t
                if h is not None and l is not None:
                    lhs += f"[{fmt_expr(h)}..{fmt_expr(l)}]"
                elif idx is not None:
                    lhs += f"[{fmt_expr(idx)}]"
                click.echo(f"{pad}{lhs} = {fmt_expr(v)}")

            case GotoStmt(label=l):
                click.echo(f"{pad}GOTO {l}")

            case CallStmt(procedure=p):
                click.echo(f"{pad}CALL {p}")

            case ExitStmt(code=c):
                click.echo(f"{pad}EXIT {fmt_expr(c)}")

            case IfStmt(condition=c, then_stmt=t):
                click.echo(f"{pad}IF {fmt_expr(c)} THEN")
                fmt_stmt(t, indent + 1)

            case ForStmt(var=v, start=s, end=e, step=st):
                step_str = f" STEP {fmt_expr(st)}" if st else ""
                click.echo(f"{pad}FOR {v} = {fmt_expr(s)} TO {fmt_expr(e)}{step_str}")

            case NextStmt(var=v):
                click.echo(f"{pad}NEXT {v}")

            case PushStmt(value=v):
                click.echo(f"{pad}PUSH {fmt_expr(v)}")

            case PopStmt(target=t, index=idx):
                lhs = t
                if idx is not None:
                    lhs += f"[{fmt_expr(idx)}]"
                click.echo(f"{pad}POP {lhs}")

            case DrScanStmt(length=l, tdi=tdi, capture=cap, compare=cmp, mask=m, result=r):
                parts = [f"DRSCAN {fmt_expr(l)}, {fmt_expr(tdi)}"]
                if cap: parts.append(f"CAPTURE {fmt_expr(cap)}")
                if cmp: parts.append(f"COMPARE {fmt_expr(cmp)}, {fmt_expr(m)}, {fmt_expr(r)}")
                click.echo(f"{pad}{', '.join(parts)}")

            case IrScanStmt(length=l, tdi=tdi, capture=cap, compare=cmp, mask=m, result=r):
                parts = [f"IRSCAN {fmt_expr(l)}, {fmt_expr(tdi)}"]
                if cap: parts.append(f"CAPTURE {fmt_expr(cap)}")
                if cmp: parts.append(f"COMPARE {fmt_expr(cmp)}, {fmt_expr(m)}, {fmt_expr(r)}")
                click.echo(f"{pad}{', '.join(parts)}")

            case DrStopStmt(state=s):
                click.echo(f"{pad}DRSTOP {s}")

            case IrStopStmt(state=s):
                click.echo(f"{pad}IRSTOP {s}")

            case StateStmt(path=p):
                click.echo(f"{pad}STATE {' '.join(p)}")

            case WaitStmt(wait_state=ws, cycles=cy, usecs=us, end_state=es):
                parts = []
                if ws: parts.append(ws)
                if cy: parts.append(f"{fmt_expr(cy)} CYCLES")
                if us: parts.append(f"{fmt_expr(us)} USEC")
                if es: parts.append(es)
                click.echo(f"{pad}WAIT {', '.join(parts)}")

            case TrstStmt(cycles=cy, usecs=us):
                parts = []
                if cy: parts.append(f"{fmt_expr(cy)} CYCLES")
                if us: parts.append(f"{fmt_expr(us)} USEC")
                click.echo(f"{pad}TRST {', '.join(parts)}" if parts else f"{pad}TRST")

            case FrequencyStmt(value=v):
                if v:
                    click.echo(f"{pad}FREQUENCY {fmt_expr(v)}")
                else:
                    click.echo(f"{pad}FREQUENCY")

            case PreDrStmt(count=c, data=d):
                s = f"PREDR {fmt_expr(c)}"
                if d: s += f", {fmt_expr(d)}"
                click.echo(f"{pad}{s}")

            case PostDrStmt(count=c, data=d):
                s = f"POSTDR {fmt_expr(c)}"
                if d: s += f", {fmt_expr(d)}"
                click.echo(f"{pad}{s}")

            case PreIrStmt(count=c, data=d):
                s = f"PREIR {fmt_expr(c)}"
                if d: s += f", {fmt_expr(d)}"
                click.echo(f"{pad}{s}")

            case PostIrStmt(count=c, data=d):
                s = f"POSTIR {fmt_expr(c)}"
                if d: s += f", {fmt_expr(d)}"
                click.echo(f"{pad}{s}")

            case PrintStmt(parts=parts):
                args = []
                for p in parts:
                    if isinstance(p, str):
                        args.append(f'"{p}"')
                    else:
                        args.append(fmt_expr(p))
                click.echo(f"{pad}PRINT {', '.join(args)}")

            case ExportStmt(key=k, value=v):
                click.echo(f"{pad}EXPORT \"{k}\", {fmt_expr(v)}")

            case VmapStmt(signals=sigs):
                click.echo(f"{pad}VMAP {', '.join(repr(s) for s in sigs)}")

            case VectorStmt(dir_vec=dv, in_vec=iv, capture=cap, compare=cmp, mask=m, result=r):
                parts = [f"VECTOR {fmt_expr(dv)}, {fmt_expr(iv)}"]
                if cap: parts.append(f"CAPTURE {fmt_expr(cap)}")
                if cmp: parts.append(f"COMPARE {fmt_expr(cmp)}, {fmt_expr(m)}, {fmt_expr(r)}")
                click.echo(f"{pad}{', '.join(parts)}")

            case _:
                click.echo(f"{pad}??? {type(stmt).__name__}")

    # --- Output ---

    # Notes
    for note in prog.notes:
        click.echo(f'NOTE "{note.key}" "{note.value}"')
    click.echo()

    # Actions
    for name, action in prog.actions.items():
        desc = f' "{action.description}"' if action.description else ''
        click.echo(f"ACTION {name}{desc}:")
        for proc_name, modifier in action.procedures:
            mod = f" [{modifier}]" if modifier else ""
            click.echo(f"    {proc_name}{mod}")
        click.echo()

    # Data blocks
    for name, data in prog.data_blocks.items():
        click.echo(f"DATA {name}:")
        for stmt in data.statements:
            fmt_stmt(stmt, 1)
        click.echo()

    # Procedures
    for name, proc in prog.procedures.items():
        uses = f" USES {', '.join(proc.uses)}" if proc.uses else ""
        click.echo(f"PROCEDURE {name}{uses}:")

        # Build reverse label map: stmt_index -> [labels]
        labels_at = {}
        for lbl, idx in proc.labels.items():
            labels_at.setdefault(idx, []).append(lbl)

        indent = 1
        for i, stmt in enumerate(proc.statements):
            if i in labels_at:
                for lbl in labels_at[i]:
                    click.echo(f"    {'    ' * (indent - 1)}{lbl}:")

            if isinstance(stmt, NextStmt):
                indent = max(1, indent - 1)

            fmt_stmt(stmt, indent)

            if isinstance(stmt, ForStmt):
                indent += 1

        click.echo()


@stapl.command(help="Run STAPL file against hardware")
@click.argument('filename', type=click.Path(exists=True))
@click.option('-r', '--root', type=base.ROOT, required=True,
              help='Path to JTAG Interface (e.g. tei-/jtag)')
@click.option('-a', '--action', 'action_name', required=True,
              help='Action to execute')
@click.option('--no-crc', is_flag=True, help="Skip CRC verification")
@click.option('--include', 'includes', multiple=True,
              help='Include optional procedure (may repeat)')
def run(filename, root, action_name, no_crc, includes):
    from ..stapl import load, Interpreter, StaplExit
    from ..stapl.player import JtagPlayer
    from ..protocol.jtag import Interface

    if not isinstance(root, Interface):
        click.echo(f"Error: root resolved to {type(root).__name__}, "
                   "expected a JTAG Interface", err=True)
        raise SystemExit(1)

    with open(filename, 'r') as f:
        source = f.read()

    click.echo(f"Loading {filename} ({len(source)} bytes)...")
    prog = load(source, check_crc=not no_crc)

    actions = list(prog.actions.keys())
    click.echo(f"Available actions: {', '.join(actions)}")

    player = JtagPlayer(root)
    interp = Interpreter(prog)

    include_set = {s.upper() for s in includes} if includes else None

    try:
        exit_code = interp.execute(action_name, player, include=include_set)
        if exit_code:
            click.echo(f"Action {action_name} failed with exit code {exit_code}",
                       err=True)
            raise SystemExit(exit_code)
        click.echo(f"Action {action_name} completed successfully.")
    except StaplExit as e:
        if e.code:
            click.echo(f"Action {action_name} failed with exit code {e.code}",
                       err=True)
            raise SystemExit(e.code)
        click.echo(f"Action {action_name} completed successfully.")


@stapl.command(help="Transpile STAPL file to Python")
@click.argument('filename', type=click.Path(exists=True))
@click.option('-o', '--output', 'output_dir', required=True,
              type=click.Path(), help="Output directory")
@click.option('--no-crc', is_flag=True, help="Skip CRC verification")
@click.option('--data-threshold', default=256, type=int,
              help="Boolean arrays >= this many bits are externalized (default: 256)")
@click.option('--config', 'config_file', type=click.Path(exists=True),
              help="YAML config file (renames, enums, bitfields)")
def transpile(filename, output_dir, no_crc, data_threshold, config_file):
    from ..stapl import load
    from ..stapl.transpile import transpile as do_transpile, TranspileConfig

    with open(filename, 'r') as f:
        source = f.read()

    if config_file:
        config = TranspileConfig.from_yaml(config_file)
        config.data_threshold = data_threshold
    else:
        config = TranspileConfig(data_threshold=data_threshold)

    prog = load(source, check_crc=not no_crc)
    source_name = Path(filename).name

    python_source, data_files = do_transpile(prog, config, source_name)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    py_file = out / "program.py"
    py_file.write_text(python_source)
    click.echo(f"Wrote {py_file}")

    if data_files:
        data_dir = out / "data"
        data_dir.mkdir(exist_ok=True)
        for name, data in data_files.items():
            path = data_dir / name
            path.write_bytes(data)
            click.echo(f"Wrote {path} ({len(data)} bytes)")

    click.echo(f"Transpilation complete: {len(data_files)} data file(s)")
