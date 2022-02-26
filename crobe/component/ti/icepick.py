from ...part_id import PartId
from ...protocol import jtag
from ...bitfield import *
from enum import *

class Block(IntEnum):
    IcePick = 0
    TestTap = 1
    DebugTap = 2

class IcePickBlock(IntEnum):
    AllZero = 0
    Control = 1
    LinkingMode = 2

class IcePickId(Bitfield):
    version = Field(24, 8)
    test_taps = Field(20, 4)
    emu_taps = Field(16, 4)
    icepick_type = Field(4, 12)
    capabilities = Field(0, 4)

class Connect(Bitfield):
    write_en = BooleanField(7)
    res = Field(4, 3)
    key = MappingField(0, 4, {9: "connected", 6: "disconnected"})

class UserCode(Bitfield):
    version = Field(28, 4)
    variant = Field(12, 16)
    res = Field(1, 11)
    one = Field(0, 1)

class SecondaryTap(Bitfield):
    all = Field(0, 24)
    visible_tap = BooleanField(9)
    select_tap = BooleanField(8)
    tap_accessible = BooleanField(1)
    tap_present = BooleanField(0)

class SecondaryTestTap(SecondaryTap):
    pass

class SecondaryDebugTap(SecondaryTap):
    inhibit_sleep = BooleanField(20)
    in_reset = BooleanField(17)
    reset_control = Field(14, 3)
    force_active = BooleanField(3)

class Router(Bitfield):
    write_en = BooleanField(31)
    block = EnumField(28, 3, Block)
    register = Field(24, 4)
    value = Field(0, 24)

class IcePick(jtag.Tap):
    fmax = 10e6
    irlen = 6
    
    CONNECT_REG = jtag.Dr(8, Connect)
    ICEPICK_ID = jtag.Dr(32, IcePickId)
    ROUTER_REG = jtag.Dr(32, Router)
    USERCODE_REG = jtag.Dr(32, UserCode)

    ROUTER = jtag.Instruction(2, "ROUTER_REG")
    IDCODE = jtag.Instruction(4, "DEVICE_ID")
    ICEPICKCODE = jtag.Instruction(5, "ICEPICK_ID")
    CONNECT = jtag.Instruction(7, "CONNECT_REG")
    USERCODE = jtag.Instruction(8, "USERCODE_REG")
    
    TAPS = {}

    def __init__(self, port, idcode):
        jtag.Tap.__init__(self, port, idcode)
        self.name = "Ti ICE-Pick"
        self.taps = {}
        self.disabled = {}

    def start(self):
        with self.port.port.freq_capped("icepick", 1e5):
            connect = self.CONNECT.cmd(Connect(write_en = True, key = "connected"))
            idcode = self.IDCODE.cmd(read_tdo = True)
            icepick_id = self.ICEPICKCODE.cmd(read_tdo = True)
            user_code = self.USERCODE.cmd(read_tdo = True)

            self.execute([connect, idcode, icepick_id, user_code])

        self.idcode = PartId.from_idcode(idcode.tdo)
        self.icepick_id = icepick_id.tdo
        self.user_code = user_code.tdo

        self.logger.note("IDCode: %s", self.idcode)
        self.logger.note("ICEPick-ID: %s", self.icepick_id)
        self.logger.note("User Code: %s", self.user_code)

        test_taps = self.block_dump(Block.TestTap, SecondaryTestTap, self.icepick_id.test_taps)
        debug_taps = self.block_dump(Block.DebugTap, SecondaryDebugTap, self.icepick_id.emu_taps)
        active = set((Block.TestTap, t) for t in test_taps) | set((Block.DebugTap, t) for t in debug_taps)

        self.tap_keys = [(Block.TestTap, t) for t in range(self.icepick_id.test_taps)] \
                        + [(Block.DebugTap, t) for t in range(self.icepick_id.emu_taps)]
        
        ir_delta = 0
        for k in self.tap_keys:
            if k not in active:
                continue
            irlen = jtag.Chain.irlen_for(self.TAPS[k])
            ir_delta += irlen
            self.taps[k] = self.port.taps_at(self.ir_pre - ir_delta)

        super().start()

    def state_dump(self):
        self.block_dump(Block.TestTap, SecondaryTestTap, self.icepick_id.test_taps)
        self.block_dump(Block.DebugTap, SecondaryDebugTap, self.icepick_id.emu_taps)
        
    def block_dump(self, block = Block.TestTap, rtype = SecondaryTestTap, count = 16):
        test_tap_cmds = []
        test_tap_reads = []
        enabled = set()
        for i in range(count):
            data = self.router_read(block, i)
            data = rtype(data)
            self.logger.note("Secondary test tap %d: %s", i, data)
            if data.select_tap:
                enabled.add(i)
        return enabled

    def router_write(self, block, register, value):
        with self.port.port.freq_capped("icepick", 1e5):
            self.execute([
                self.ROUTER.cmd(Router(write_en = True,
                                       block = int(block),
                                       register = int(register),
                                       value = int(value))),
                self.cmd_run(10),
            ])

    def router_read(self, block, register):
        with self.port.port.freq_capped("icepick", 1e5):
            r = self.ROUTER.cmd(read_tdo = True)

            self.execute([
                self.ROUTER.cmd(Router(block = int(block), register = int(register))),
                self.cmd_run(10),
                r,
                self.cmd_run(1),
            ])
            return Router(all = r.tdo).value
        
    def tap_enable(self, block, index, enable = True):
        key = (block, index)
        self.logger.trace("Setting TAP#%s/%d enable to %s", block, index, enable)
        self.logger.debug("Currently enabled: %s", self.taps.keys())

        if bool(key in self.taps) == bool(enable):
            return

        cur = SecondaryTap(all = self.router_read(block = block, register = index))
#        if enable:
#            if not cur.tap_present:
#                raise ValueError("TAP is not present")
#            if not cur.tap_accessible:
#                raise ValueError("TAP is not accessible")

        cur.select_tap = enable
        self.router_write(block, index, int(cur))

        ir_delta = 0
        dr_delta = 0
        for k in self.tap_keys:
            if k <= key and k in self.taps:
                ir_delta += jtag.Chain.irlen_for(self.TAPS[k])
                dr_delta += 1

        if enable:
            r = self.chain_insert_tap(self.ir_pre - ir_delta, self.dr_pre - dr_delta, key)
        else:
            r = self.chain_remove_tap(self.ir_pre - ir_delta, self.dr_pre - dr_delta, key)

        self.logger.trace("%s TAP#%s/%d done", "Enabling" if enable else "Disabling", block, index)
        return r

    def chain_insert_tap(self, ir_pre, dr_pre, key):
        self.logger.trace("Inserting tap %s, @ir %d dr %d", key, ir_pre, dr_pre)
        idcode = self.TAPS[key]
        irlen = jtag.Chain.irlen_for(idcode)

        interface = self.port.port

        with interface.freq_capped("icepick", 1e5):
            total_irlen_before = self.port.total_irlen
            interface.capture_ir()
            captured_ir = interface.shift_discover(shift_in = -1)
            ir_length = len(captured_ir)

            assert total_irlen_before + irlen == ir_length

        chain = self.port
        chain.splice(ir_pre, irlen, 1)

        if key in self.disabled:
            taps = self.disabled[key]
            del self.disabled[key]

            for t in taps:
                self.logger.debug("Reenabling %s", t)
                chain.child_add(t)
                t.port = chain
                t.position_set(ir_pre, dr_pre)
        else:
            taps = self.port.tap_add(idcode, irlen, ir_pre, dr_pre)

        self.taps[key] = taps
        return taps

    def chain_remove_tap(self, ir_pre, dr_pre, key):
        self.logger.trace("Removing tap %s, @ir %d dr %d", key, ir_pre, dr_pre)
        idcode = self.TAPS[key]
        irlen = jtag.Chain.irlen_for(idcode)

        interface = self.port.port

        with interface.freq_capped("icepick", 1e5):
            total_irlen_before = self.port.total_irlen
            interface.capture_ir()
            captured_ir = interface.shift_discover(shift_in = -1)
            ir_length = len(captured_ir)

            assert total_irlen_before - irlen == ir_length

        chain = self.port

        taps = chain.taps_at(ir_pre)
        for t in taps:
            self.logger.debug("Disabling %s", t)
            chain.child_remove(t)
            t.ir_pre = t.ir_post = t.dr_pre = t.dr_post = None
            t.port = None
        self.disabled[key] = taps
        del self.taps[key]

        chain.splice(ir_pre, -irlen, -1)
