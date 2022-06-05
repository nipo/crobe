from ...protocol import jtag
from ... import bitfield
import enum
from . import dm

class IrReg(jtag.InstructionRegistry):
    class CS(bitfield.Bitfield):
        all          = bitfield.Field(0, 32)
        version      = bitfield.Field(0, 4)
        abits        = bitfield.Field(4, 6)
        dmistat      = bitfield.Field(10, 2)
        idle         = bitfield.Field(12, 3)
        dmireset     = bitfield.BooleanField(16)
        dmihardreset = bitfield.BooleanField(17)

    DTMCS_REG = jtag.Dr(32, type = CS)
    DMI_REG = jtag.Dr(None)

    IDCODE               = jtag.Instruction(0x01, "DEVICE_ID")
    DTMCS                = jtag.Instruction(0x10, "DTMCS_REG")
    DMI                  = jtag.Instruction(0x11, "DMI_REG")
    # 12..17 are reserved

class Tap(IrReg):
    def __init__(self):
        self.abits = 0

    def dmi_execute(self, operations):
        lower = []
        last_read = None

        reads = {}
        
        self.logger.protocol("Running %s", operations)
        
        for o in operations:
            if isinstance(o, dm.Read):
                dmi = self.Dmi(address = o.address,
                               data = 0,
                               op = 1)
                cmd = self.DMI.cmd(dmi, read_tdo = last_read is not None,
                                   pre_dr_run = 30)
                lower.append(cmd)
                if last_read:
                    reads[last_read] = cmd
                last_read = o
            elif isinstance(o, dm.Write):
                dmi = self.Dmi(address = o.address,
                                    data = int(o.data),
                                    op = 2)
                cmd = self.DMI.cmd(dmi, read_tdo = last_read is not None,
                                   pre_dr_run = 30)
                lower.append(cmd)
                if last_read:
                    reads[last_read] = cmd
                last_read = None
            else:
                raise ValueError(o)
            lower.append(self.cmd_run(10))
        if last_read:
            cmd = self.DMI.cmd(0, read_tdo = True)
            lower.append(cmd)
            reads[last_read] = cmd
            lower.append(self.cmd_run(10))

        self.execute(lower)
        for o, read in reads.items():
            o.data = read.tdo.data
            if read.tdo.op == 3:
                self.logger.warning("Pending operation did not complete soon enough")
            o.success = read.tdo.op == 0

    def start(self):
        dtmcs = self.DTMCS.shift(0, read_tdo = True,
                                 pre_dr_run = 30)
        self.abits = dtmcs.abits

        self.logger.note("Risc-V DTM CS: %#010x %s",
                         int(dtmcs), dtmcs)

        class Dmi(bitfield.Bitfield):
            all     = bitfield.Field(0, dtmcs.abits + 32 + 2)
            op      = bitfield.Field(0, 2)
            data    = bitfield.Field(2, 32)
            address = bitfield.Field(34, 32 + 2)

        self.Dmi = Dmi
        self.DMI.dr = jtag.TapDr(self, "DMI_REG",
                                 dtmcs.abits + 32 + 2,
                                 type = Dmi)

        self.logger.note("Risc-V JTAG DTM v. %d, %d address bits",
                         dtmcs.version, dtmcs.abits)
        
        next_dm = 0
        dm_index = 0
        while next_dm is not None:
            self.logger.note("Adding DM at %#010x", next_dm)
            dm_inst = dm.DebugModule(self, idcode = self.idcode, base = next_dm, index = dm_index).cast()
            next_dm = dm_inst.next_base_get() or None
            self.child_add(dm_inst)
            dm_index += 1
