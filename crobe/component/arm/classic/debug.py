from ....model import Component, PortComponent
from ....util.endian import swib_u32
from ....protocol import jtag
import enum
import time
from .embedded_ice import *
import functools
from . import armv5

class Debug(PortComponent):
    """
    Passed port must be a ARM classic TAP.
    """

    def __init__(self, port):
        super().__init__(port, "Debug")

    def lower(self, op_list):
        ret = []
        scan_chain = None

        for op in op_list:

            if isinstance(op, Op):
                op.__result_to = None

                if op.scan_chain != scan_chain:
                    scan_chain = op.scan_chain
                    ret.append(self.port.SCAN_N.cmd(self.port.PathSelect[scan_chain],
                                                    read_tdo = False))

                ret += op.ops(self.port)

            elif isinstance(op, jtag.TapOperation):
                ret.append(op)
                scan_chain = None

            else:
                raise ValueError("Unknown operation type", op)

        return ret

    def execute(self, op_list):
        tap_ops = self.lower(op_list)
        return self.port.execute(tap_ops)
    
    def cmd_ice(self, addr, data = None):
        return IceScan(addr, data = data)

    def cmd_debug(self, instr, data = None,
                  sysspeed = False, wptandbkpt = False,
                  read_data = False):
        return DebugScan(instr, data = data,
                         sysspeed = sysspeed, wptandbkpt = wptandbkpt,
                         read_data = read_data)
    
    def ice(self, addr, data = None):
        cmd = self.cmd_ice(addr, data)
        self.execute([cmd])
        return cmd.rdata

    def debug(self, instr, data = None,
              sysspeed = False, wptandbkpt = False,
              read_data = False):
        cmd = self.cmd_debug(instr, data = data,
                             sysspeed = sysspeed, wptandbkpt = wptandbkpt,
                             read_data = read_data)
        self.execute([cmd])
        return cmd.rdata

    def cmd_watch(self, no, **kwargs):
        return WatchPointSetup(no, **kwargs)

    def debug_control(self, **kwargs):
        control = DebugControl(self.ice(Register.DebugCtrl))
        old = int(control)
        for name, value in kwargs.items():
            setattr(control, name, value)
        if int(control) != old:
            self.ice(Register.DebugCtrl, control)
        return control
    
    def debug_enable(self):
        self.debug_control(disable = False, intdis = False, dbgack = False, dbgrq = False, monitor = False)

    def debug_disable(self):
        self.execute([
            self.cmd_ice(Register.DebugCtrl, DebugControl(disable = 1)),
            self.port.RESTART.cmd(),
        ])

    def halt_wait(self, timeout = 1, **kwargs):
        deadline = time.time() + timeout
        while True:
            r = DebugStatus(self.ice(Register.DebugStatus))

            ok = r.dbgack
            for name, value in kwargs.items():
                ok = ok and (getattr(r, name) == value)

            if ok:
                return r

            if time.time() < deadline:
                time.sleep(.05)
                continue
            raise RuntimeError(f"Cannot halt target, status = {r}")
    
    def halt(self, use_dbgreq = False):
        if use_dbgreq:
            self.execute([
                self.cmd_ice(Register.DebugCtrl, DebugControl(dbgrq = True)),
                self.cmd_watch(0),
                self.cmd_watch(1),
            ])
        else:
            self.execute([
                self.cmd_ice(Register.DebugCtrl, DebugControl(dbgrq = False)),
                self.cmd_watch(0, address = 0, address_mask = 0, instruction = 0, instruction_mask = 0),
                self.cmd_watch(1),
            ])
        self.halt_wait()
        self.debug_control(dbgack = True, dbgrq = False)

    def cmd_mcr(self, coprocessor, op1, crn, crm, op2, value):
        pass

    def mcr(self, coprocessor, op1, crn, crm, op2, value):
        op = self.cmd_mcr(coprocessor, op1, crn, crm, op2, value)
        self.execute([op])
        
    def reg_read(self, no):
        regs = self.regs_read(set([no]))
        return regs[no]

    def reg_write(self, no, value):
        self.regs_write({no: value})

    def regs_read(self, nos):
        command = RegsRead(set(nos))
        self.execute([command])
        return command.values

    def regs_write(self, reg_map):
        self.execute([RegsWrite(reg_map)])

    def asm_run(self, opcodes, *, sysspeed = False):
        commands = [
            self.cmd_watch(0, address = 0, address_mask = 0, instruction = 0, instruction_mask = 0),
        ]
        for i, op in enumerate(opcodes):
            is_last = i == len(opcodes) - 1

            commands.append(self.cmd_debug(op, sysspeed = is_last and sysspeed))

        if sysspeed:
            commands += [
                self.port.RESTART.cmd(),
                self.port.cmd_run(1),
            ]
            self.execute(commands)
            self.halt_wait(syscomp = True)
        else:
            self.execute(commands)
        
    def mem_read(self, addr, size):
        # Align base address
        offset = addr & 0x3
        addr -= offset
        size += offset

        data = b''

        self.debug_control(dbgack = False)

        while len(data) < size:
            # Set base address
            self.reg_write(0, addr + len(data))

            # Read as much memory as possible to r1-r14
            reg_count = ((size - len(data)) + 3) // 4
            if reg_count > 14:
                reg_count = 14
            mask = (1 << reg_count) - 1

            self.logger.debug("Loading %d regs at 0x%08x", reg_count, addr + len(data))

            self.asm_run([
                armv5.ldmia(0, mask << 1, update = True),
                armv5.nop(),
            ], sysspeed = True)

            # Read matching registers
            regs = self.regs_read(set(range(1, reg_count + 1)))

            # Append to blob
            for no in range(1, reg_count + 1):
                data += regs[no].to_bytes(4, "little")

        self.debug_control(dbgack = True)

        # Drop initial alignment
        return data[offset:size]
            
    def mem_write(self, addr, data):
        # Dont support misalignment for now
        if addr & 0x3:
            raise ValueError(f"Unaligned address {addr:x}")
        if len(data) & 0x3:
            raise ValueError(f"Unaligned blob")

        self.debug_control(dbgack = False)

        # Set base address
        self.reg_write(0, addr)

        while data:
            # Select at most 14 words to write
            reg_count = len(data) // 4
            if reg_count > 14:
                reg_count = 14
            mask = (1 << reg_count) - 1

            # Fill data to write in r1-r14
            regs = {}
            for i in range(reg_count):
                regs[i+1] = int.from_bytes(data[:4], "little")
                data = data[4:]

            self.regs_write(regs)

            # Commit to RAM
            self.asm_run([
                armv5.stmia(0, mask << 1, update = True),
                armv5.nop(),
            ], sysspeed = True)
        self.debug_control(dbgack = True)

class Op(object):
    scan_chain = None

    def tdi(self):
        return 0

    def tdo_set(self, tdo):
        pass
    
class IceScan(Op):
    scan_chain = "Ice"

    def __init__(self, addr, data = None):
        self.addr = int(addr) & 0x1f
        self.wdata = data
        self.rdata = None

    def ops(self, tap):
        self.__Ice = tap.Ice

        ret = []
        cmd = tap.INTEST_ICE.cmd(
            dr = self.__Ice(write = self.wdata is not None,
                         addr = self.addr,
                         data = self.wdata or 0),
            read_tdo = False,
        )
        ret.append(cmd)
        if self.wdata is None:
            cmd = tap.INTEST_ICE.cmd(
                dr = self.__Ice(write = False,
                             addr = self.addr,
                             data = 0),
                read_tdo = True,
            )

            cmd.postprocess = self.tdo_handle
            ret.append(cmd)

        return ret

    def tdo_handle(self, tdo):
        v = self.__Ice(tdo)
        self.rdata = v.data
        return v

class DebugScan(Op):
    scan_chain = "Debug"

    def __init__(self,
                 instr, data = None,
                 sysspeed = False, wptandbkpt = False,
                 read_data = False):
        self.instr = instr
        self.wdata = data
        self.sysspeed = sysspeed
        self.wptandbkpt = wptandbkpt
        self.rdata = None
        self.read_data = read_data

    def ops(self, tap):
        self.__Debug = tap.Debug

        ret = []
        cmd = tap.INTEST_DEBUG.cmd(
            dr = self.__Debug(data = self.wdata or 0,
                              wptandbkpt = self.wptandbkpt,
                              sysspeed = self.sysspeed,
                              instr = swib_u32(self.instr),
            ),
            read_tdo = self.read_data,
        )
        if self.read_data:
            cmd.postprocess = self.tdo_handle
        ret.append(cmd)
        ret.append(tap.cmd_run(1))
        return ret

    def tdo_handle(self, tdo):
        v = self.__Debug(tdo)
        self.rdata = v.data
        return v

class WatchPointSetup(Op):
    scan_chain = "Ice"

    def __init__(self, no, *,
                 address = None, address_mask = 0xffffffff,
                 data = None, data_mask = 0xffffffff,
                 instruction = None, instruction_mask = 0xffffffff,
                 write = None,
                 privileged = None,
                 dbgext = None,
                 chain = None,
                 range = None,
                 dmas = None,
                 thumb = None,
                 jazelle = None):

        self.no = no
        self.address = address
        self.address_mask = address_mask
        self.data = data
        self.data_mask = data_mask
        self.instruction = instruction
        self.instruction_mask = instruction_mask
        self.write = write
        self.privileged = privileged
        self.dbgext = dbgext
        self.chain = chain
        self.range = range
        self.dmas = dmas
        self.thumb = thumb
        self.jazelle = jazelle

        self.enable = any(x is not None for x in [address, data, instruction, privileged, dbgext, chain, range, dmas, thumb, jazelle])
        self.instruction_bkpt = any(x is not None for x in [instruction, thumb, jazelle])

    def ops(self, tap):
        offset = Register.Wpt1AddrValue - Register.Wpt0AddrValue if self.no else 0
        control = WatchControl()
        control_mask = WatchControl()

        if self.instruction_bkpt:
            control.data = 0
            control.thumb = self.thumb or False
            control.jazelle = self.jazelle or False
            control_mask.thumb = self.thumb is not None
            control_mask.jazelle = self.jazelle is not None
        else:
            control.data = 1
            control.dmas = self.dmas or 0
            control_mask.dmas = 3 if self.dmas is not None else 0

        control.privileged = self.privileged or False
        control_mask.privileged = self.privileged is not None

        control.dbgext = self.dbgext or False
        control_mask.dbgext = self.dbgext is not None

        control.chain = self.chain or False
        control_mask.chain = self.chain is not None

        control.range = self.range or False
        control_mask.range = self.range is not None

        control.enable = False

        ops = []

        # In any case, emit disabled control first
        ops.append(IceScan(offset + Register.Wpt0ControlValue, int(control)))
        ops.append(IceScan(offset + Register.Wpt0ControlMask, ~int(control_mask) & ~0x8))

        if self.enable:
            # Update address / data mask if needed
            ops.append(IceScan(offset + Register.Wpt0AddrValue, self.address or 0))
            ops.append(IceScan(offset + Register.Wpt0AddrMask, ~self.address_mask))
            if self.instruction_bkpt:
                ops.append(IceScan(offset + Register.Wpt0DataValue, self.instruction or 0))
                ops.append(IceScan(offset + Register.Wpt0DataMask, ~self.instruction_mask))
            else:
                ops.append(IceScan(offset + Register.Wpt0DataValue, self.data or 0))
                ops.append(IceScan(offset + Register.Wpt0DataMask, ~self.data_mask))

            # Lastly, enable back
            control.enable = True
            ops.append(IceScan(offset + Register.Wpt0ControlValue, int(control)))

        ret = []
        for o in ops:
            ret += o.ops(tap)
        return ret

class RegsRead(Op):
    scan_chain = "Debug"

    def __init__(self, nos):
        self.nos = nos
        self.values = {}

    def ops(self, tap):
        self.__Debug = tap.Debug

        reg_map = sum((1 << x) for x in self.nos)

        ops = [
            DebugScan(armv5.stmia(0, reg_map)),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
        ]
        ret = []
        for o in ops:
            ret += o.ops(tap)

        for no in sorted(self.nos):
            ret += DebugScan(armv5.nop(), read_data = True).ops(tap)
            ret[-2].postprocess = functools.partial(self.tdo_handle, no)
        return ret

    def tdo_handle(self, no, tdo):
        v = self.__Debug(tdo)
        self.values[no] = v.data

class XpsrRead(Op):
    scan_chain = "Debug"

    def __init__(self, spsr):
        self.spsr = spsr
        self.value = None

    def ops(self, tap):
        self.__Debug = tap.Debug

        ops = [
            DebugScan(armv5.mrs(0, int(bool(self.spsr)))),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.str(0, 15)),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop(), read_data = True),
        ]
        ret = []
        for o in ops:
            ret += o.ops(tap)
        ret[-2].postprocess = self.tdo_handle
        return ret

    def tdo_handle(self, tdo):
        v = self.__Debug(tdo)
        self.value = v.data

class XpsrWrite(Op):
    scan_chain = "Debug"

    def __init__(self, spsr, value):
        self.spsr = spsr
        self.value = value

    def ops(self, tap):
        self.__Debug = tap.Debug

        ops = [
            DebugScan(armv5.msr_imm(self.value & 0xff, 0, 1, int(bool(self.spsr)))),
            DebugScan(armv5.msr_imm((self.value >> 8) & 0xff, 0xc, 2, int(bool(self.spsr)))),
            DebugScan(armv5.msr_imm((self.value >> 16) & 0xff, 0x8, 4, int(bool(self.spsr)))),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.msr_imm((self.value >> 24) & 0xff, 0x4, 8, int(bool(self.spsr)))),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
        ]
        ret = []
        for o in ops:
            ret += o.ops(tap)
        ret[-2].postprocess = self.tdo_handle
        return ret

    def tdo_handle(self, tdo):
        v = self.__Debug(tdo)
        self.value = v.data

class RegsWrite(Op):
    scan_chain = "Debug"

    def __init__(self, values):
        assert 15 not in values
        self.values = values

    def ops(self, tap):
        reg_map = sum((1 << x) for x in self.values)
        commands = [
            DebugScan(armv5.ldmia(0, reg_map)),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            ]
        for no, value in sorted(self.values.items()):
            commands += [
                DebugScan(armv5.nop(), data = value),
            ]
        commands += [
            DebugScan(armv5.nop()),
        ]

        ret = []
        for o in commands:
            ret += o.ops(tap)
        return ret
