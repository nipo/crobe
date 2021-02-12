from ....model import Component, PortComponent
from ....util.endian import swib_u32
from ....protocol import jtag
import enum
import time
from .embedded_ice import *
import functools
from . import armv5

class CpuContext:
    def __init__(self, **regs):
        self.regs = regs

    def save(self, debug):
        pass

    def restore(self, debug):
        pass

class Arm926Context(CpuContext):
    def save(self, debug):
        cmds = [
            XpsrRead(False),
            XpsrRead(True),
            RegsRead(range(0, 16)),
            ]
        debug.execute(cmds)
        self.regs["cpsr"] = cmds[0].value
        self.regs["spsr"] = cmds[1].value
        for no, value in cmds[2].values.items():
            self.regs[f"r{no:02d}"] = value

    def restore(self, debug):
        cmds = [
            XpsrWrite(False, self.regs["cpsr"]),
            XpsrWrite(True, self.regs["spsr"]),
            RegsWrite({i:self.regs[f"r{i:02d}"] for i in range(15)}),
            ]
        debug.execute(cmds)

    @classmethod
    def normalized(cls):
        return cls(
            cpsr = 0xd3,
            spsr = 0,
            r0 = 0, r1 = 0, r2 = 0, r3 = 0,
            r4 = 0, r5 = 0, r6 = 0, r7 = 0,
            r8 = 0, r9 = 0, r10 = 0, r11 = 0,
            r12 = 0, r13 = 0, r14 = 0, r15 = 0,
        )

    def dump(self):
        for k, v in sorted(self.regs.items()):
            print(f"{k}: {v:#010x}")
    
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

    def vector_catch_control(self, field):
        self.ice(Register.VectorCatchCtrl, field)
    
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

    def is_running(self):
        r = DebugStatus(self.ice(Register.DebugStatus))
        return not r.dbgack

    def moe(self):
        r = DebugStatus(self.ice(Register.DebugStatus))
        return Moe(r.moe)
        
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
        if coprocessor == 15:
            return Cp15Scan(op1, op2, crn, crm, value)
        raise NotImplemented("Cannot access other CP than 15")

    def mcr(self, coprocessor, op1, crn, crm, op2, value):
        op = self.cmd_mcr(coprocessor, op1, crn, crm, op2, value)
        self.execute([op])
        
    def cmd_mrc(self, coprocessor, op1, crn, crm, op2):
        if coprocessor == 15:
            return Cp15Scan(op1, op2, crn, crm)
        raise NotImplemented("Cannot access other CP than 15")

    def mrc(self, coprocessor, op1, crn, crm, op2):
        op = self.cmd_mrc(coprocessor, op1, crn, crm, op2)
        self.execute([op])
        return op.rdata
        
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
        for i, o in enumerate(opcodes):
            print(f"asm run {i:d}: {o:08x}")
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

        self.logger.info("Reading at %#10x: %d bytes", addr, size)

        self.debug_control(dbgack = False)

        while len(data) < size:
            # Set base address
            base = addr + len(data)
            self.reg_write(14, base)

            # Read as much memory as possible to r0-r13
            reg_count = (size - len(data) + 3) // 4
            if reg_count > 14:
                reg_count = 14
            mask = (1 << reg_count) - 1

            self.logger.debug("Loading %d regs at 0x%08x", reg_count, base)

            self.asm_run([
                armv5.ldmia(14, mask, update = True),
                armv5.nop(),
            ], sysspeed = True)

            # Read matching registers
            regs = self.regs_read(set(range(reg_count)))

            # Append to blob
            for no in range(reg_count):
                data += regs[no].to_bytes(4, "little")

        self.debug_control(dbgack = True)

        # Drop initial alignment
        data = data[offset:size]
        
        self.logger.debug("-> %s", data.hex())

        return data
            
    def mem_write(self, addr, data):
        # Dont support misalignment for now
        if addr & 0x3:
            raise ValueError(f"Unaligned address {addr:x}")
        if len(data) & 0x3:
            raise ValueError(f"Unaligned blob")

        self.logger.info("Writing %d bytes at %#10x", len(data), addr)
        self.logger.debug("<- %s", data.hex())
        
        self.debug_control(dbgack = False)

        while data:
            # Select at most 14 words to write
            reg_count = len(data) // 4
            if reg_count > 14:
                reg_count = 14
            mask = (1 << reg_count) - 1

            # Set base address
            regs = {14 : addr}

            # Fill data to write in r0-r13
            for i in range(reg_count):
                regs[i] = int.from_bytes(data[:4], "little")
                data = data[4:]
                addr += 4

            self.regs_write(regs)

            # Commit to RAM
            self.asm_run([
                armv5.stmia(14, mask, update = True),
                armv5.nop(),
            ], sysspeed = True)
        self.debug_control(dbgack = True)
            
    def resume(self, pc,
               intdis = False,
               dbgack = False,
               disable = False,
               monitor = False):
        self.logger.info("Resuming execution at %#10x", pc)
        self.debug_control(dbgack = dbgack,
                           intdis = intdis,
                           monitor = monitor,
                           disable = disable)
        commands = [
            self.cmd_watch(0),
            self.cmd_watch(1),
            ResumeAt(pc),
        ]
        self.execute(commands)

    def dcc_pop_fast(self, count):
#        self.logger.info("Popping %d DCC items", count)
        rsp = []
        while len(rsp) < count:
            cmds = [IceScan(Register.CommData) for x in range(count - len(rsp))]
            self.execute(cmds)
            for r in cmds:
                if r.rdata_valid:
                    rsp.append(r.rata)
        return rsp

    def dcc_pop(self, count):
        self.logger.debug("Popping %d DCC items", count)
        rsp = []
        for i in range(count):
            self.logger.debug("Popping DCC value")
            filled = False
            for i in range(100):
                rd = IceScan(Register.CommCtrl)
                self.execute([rd])
                filled = CommControl(all = rd.rdata).cpu_to_debug
                if filled:
                    break
            if not filled:
                raise RuntimeError("DCC Register never filled")
            rd = IceScan(Register.CommData)
            self.execute([rd])
            self.logger.debug("-> %#10x", rd.rdata)
            rsp.append(int(rd.rdata))
        return rsp

    def dcc_flush(self, count = 15):
        self.logger.debug("Clearing DCC")
        cmds = [IceScan(Register.CommData) for x in range(count)]
        self.execute(cmds)
        count = 0
        for r in cmds:
            if r.rdata_valid:
                count += 1
        self.logger.debug("-> %d entries cleared", count)

    def dcc_push_nohs(self, data_list):
#        self.logger.debug("Pushing DCC items: %s", ', '.join(hex(d) for d in data_list))
        cmds = [IceScan(Register.CommData, x) for x in data_list]
        self.execute(cmds)

    def dcc_push(self, data_list):
        for d in data_list:
            self.logger.debug("Pushing DCC value: %#10x", d)
            free = False
            for i in range(100):
                rd = IceScan(Register.CommCtrl)
                self.execute([rd])
                free = not CommControl(all = rd.rdata).debug_to_cpu
                if free:
                    break
            if not free:
                raise RuntimeError("DCC Register never freed")
            self.execute([IceScan(Register.CommData, d)])

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
        self.rdata_valid = None

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
        self.rdata_valid = v.addr & 1
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

class Cp15Scan(Op):
    scan_chain = "Cp15"

    def __init__(self, op1, op2, crn, crm, data = None):
        self.op1 = op1
        self.op2 = op2
        self.crn = crn
        self.crm = crm
        self.wdata = data
        self.rdata = None

    def ops(self, tap):
        self.__Cp15 = tap.Cp15

        reg = self.__Cp15(data = self.wdata or 0,
                          access = 1,
                          op1 = self.op1,
                          op2 = self.op2,
                          crn = self.crn,
                          crm = self.crm,
                          write = self.wdata is not None,
        )
        
        ret = [tap.INTEST_CP15.cmd(dr = reg)]
        ret.append(tap.cmd_run(1))

        if self.wdata is None:
            ret += [
                tap.INTEST_CP15.cmd(dr = self.__Cp15()),
                tap.cmd_run(1),
            ]
            ret[-2].postprocess = self.tdo_handle
        return ret

    def tdo_handle(self, tdo):
        v = self.__Cp15(tdo)
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

        for i in ret:
            if isinstance(i, jtag.TapRun):
                print("run")
            elif isinstance(i, jtag.TapDrShift):
                print("shift %x" % (int(i.tdi) >> 35))

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

class RegsWriteSlow(Op):
    scan_chain = "Debug"

    def __init__(self, values):
        assert 15 not in values
        self.values = values

    def ops(self, tap):
        commands = []
        for no, value in sorted(self.values.items()):
            commands += [
                DebugScan(armv5.movi(no, value & 0xff)),
            ]
            for byte in range(1, 4):
                i = value & (0xff << (8 * byte))
                if i:
                    commands += [
                        DebugScan(armv5.ori(no, no, i)),
                    ]
        commands += [
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
        ]

        ret = []
        for o in commands:
            ret += o.ops(tap)
        return ret

class ResumeAt(Op):
    scan_chain = "Debug"

    def __init__(self, pc):
        self.pc = pc

    def ops(self, tap):
        commands = [
            DebugScan(armv5.ldmia(0, 0x8000, 0)),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop(), data = self.pc),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop()),
            DebugScan(armv5.nop(), sysspeed = 1),
        ]

        ret = []
        for o in commands:
            ret += o.ops(tap)
        ret += [
            tap.BYPASS.cmd(),
            tap.cmd_run(1),
            tap.RESTART.cmd(),
            tap.cmd_run(1),
            tap.BYPASS.cmd(),
            tap.cmd_run(1),
        ]
        return ret
