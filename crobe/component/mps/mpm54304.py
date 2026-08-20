from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
from ...util.pretty import metric
import enum
import math
import time

class Mpm54304(i2c.AddressedSlave):
    _by_addr = {}
    _by_class = {}

    @classmethod
    def at(cls, address):
        def _dec(reg_class):
            cls._by_addr[address] = reg_class
            cls._by_class[reg_class] = address
            return reg_class
        return _dec

    def __init__(self, bus, saddr):
        super().__init__(bus, "mpm54304", saddr)

    def reg_read(self, reg):
        try:
            addr = int(reg)
        except TypeError:
            addr = self._by_class[reg]
        reg_class = self._by_addr[addr]

        reg_size = (reg_class._width + 7) // 8

        raw = super().mem_read(addr, reg_size)
        value = int.from_bytes(raw, "little")
        pretty = reg_class(value)

        self.logger.trace("Reg read %s (%02x): %s (%s)", reg_class.__name__, reg, pretty, raw.hex())

        return pretty

    def reg_write(self, reg, value = None):
        if value is None:
            value = int(reg)
            reg = reg.__class__

        try:
            addr = int(reg)
        except TypeError:
            addr = self._by_class[reg]
        reg_class = self._by_addr[addr]

        pretty = reg_class(int(value))

        reg_size = (reg_class._width + 7) // 8
        raw = int(value).to_bytes(reg_size, "little")

        self.logger.trace("Reg write %s (%02x): %s (%s)", reg_class.__name__, reg, pretty, raw.hex())
        self.port.execute([i2c.Write(self.saddr, bytes([addr]) + raw)])

    def dump_configuration(self):
        print("Selected output voltages:")
        for buck, addr in sorted(self._VOUT_REG_ADDR.items()):
            reg = self.reg_read(addr)
            actual = reg.vref * (3 if reg.vout_select else 1)
            print("  Vout%d = %.3fV  (vout_select=%d, vref=%.3fV, reg 0x%02x = 0x%02x)"
                  % (buck, actual, reg.vout_select, reg.vref, addr, int(reg)))
        print()

        for addr in sorted(self._by_addr):
            reg_class = self._by_addr[addr]
            reg = self.reg_read(addr)
            print("0x%02x %s:" % (addr, reg_class.__name__))
            reg.dump_pretty(print)
            print()
            print()

    # Buck N's Vout_Select/V_Ref register address (p.29)
    _VOUT_REG_ADDR = {1: 0x02, 2: 0x05, 3: 0x08, 4: 0x0B}

    # Direct mode (Vout_Select=0): Vout = Vref, 0.55-1.82V.
    # Divided mode (Vout_Select=1): Vout = 3xVref, 1.65-5.46V.
    # Direct mode is preferred where it reaches (finer 10mV steps at
    # the output, vs. 30mV steps through the /3 divider).
    def compute_vout_reg(self, buck, voltage):
        addr = self._VOUT_REG_ADDR[buck]
        reg_class = self._by_addr[addr]

        if 0.55 <= voltage <= 1.82:
            vout_select, vref = False, voltage
        elif 1.65 <= voltage <= 5.46:
            vout_select, vref = True, voltage / 3
        else:
            raise ValueError(
                "Vout%d=%.3fV is out of range (0.55-1.82V direct, or 1.65-5.46V via the /3 divider)"
                % (buck, voltage))

        return reg_class(vout_select = vout_select, vref = vref)

    def set_vout(self, buck, voltage):
        reg = self.compute_vout_reg(buck, voltage)
        self.reg_write(reg)
        return reg

    # MTP unlock password and exit code: NOT published in the datasheet
    # (p.29-30 only says "the correct password must be entered into
    # this register", no value given). Confirmed correct by MPS staff
    # (MPSnow_Nouman) on their own forum:
    # forum.monolithicpower.com/t/programming-mtp-mpm54304/3383
    _MTP_UNLOCK_SEQUENCE = (0x95, 0x63)
    _MTP_EXIT_CODE = 0x49
    _MTP_BURN_TIMEOUT_S = 1.0
    _MTP_BURN_POLL_S = 0.02

    # Registers 0x00-0x0D and 0x0F-0x10 are the persistent config that
    # gets burned. 0x0E is handled separately (its mtp_program bit is
    # the trigger, not part of the config snapshot) and 0x11 is the
    # write-only password register, not config.
    _MTP_CONFIG_REGS = [a for a in range(0x00, 0x11) if a != 0x0E]

    def burn_mtp(self):
        """Burn the current I2C register contents (0x00-0x13) into MTP.

        MTP is two-time programmable -- this is a real e-fuse write
        with no undo. Caller is responsible for having reviewed the
        full configuration (dump_configuration) and for having
        sufficient VIN margin before calling this (comfortably above
        the datasheet's 5.1V minimum, to avoid a burn that doesn't
        complete).

        Per a real-world report on the same forum thread as the
        password (kirsty.lehmann, same thread): registers that were
        only ever loaded from a prior MTP page and never explicitly
        written over I2C this session do NOT get captured as their
        current value when burning -- they fall back to some other
        (undocumented) value instead. This bit us once: without the
        rewrite-everything step below, only the 4 Vout registers we'd
        explicitly written came out correct after a burn; everything
        else we'd only read got scrambled, and current_mtp_page_index
        landed on an undocumented value (2) instead of the expected
        PAGE3. Adding the rewrite-everything step below fixed it on a
        second burn attempt on that same chip: current_mtp_page_index
        correctly advanced to PAGE3, checksum_flag stayed clean, and
        every register (not just Vout) came out matching what was live
        before the burn, confirmed surviving a full VIN power-cycle.
        """
        for addr in self._MTP_CONFIG_REGS:
            current = self.reg_read(addr)
            self.reg_write(addr, int(current))

        for code in self._MTP_UNLOCK_SEQUENCE:
            self.reg_write(0x11, code)

        gpio = self.reg_read(0x0E)
        gpio.mtp_program = True
        self.reg_write(gpio)

        deadline = time.monotonic() + self._MTP_BURN_TIMEOUT_S
        while time.monotonic() < deadline:
            time.sleep(self._MTP_BURN_POLL_S)
            gpio = self.reg_read(0x0E)
            if not gpio.mtp_program:
                break
        else:
            self.reg_write(0x11, self._MTP_EXIT_CODE)
            raise TimeoutError(
                "MTP_Program bit did not self-clear within %.1fs -- burn may not have completed"
                % self._MTP_BURN_TIMEOUT_S)

        self.reg_write(0x11, self._MTP_EXIT_CODE)

        return self.reg_read(0x13)

@i2c.Interface.db.register("mpm54304")
def mpm_get(bus):
    return Mpm54304(bus, None)

# Shared base for buck 1-4 soft-start registers (0x00, 0x03, 0x06, 0x09)
class BuckSoftStart(Bitfield):
    """Soft-start delay and reference slew rate. R/W"""
    soft_start_delay = ScaledField(4, 2, scale=0.001,
                                   doc="Delay from EN=high to Vout ramp start, s")
    additional_phase_delay = BooleanField(3, doc="Add 100ns phase delay to HS turn-on edge")
    soft_start_time = MappingField(0, 3, {
        0b000: 2.67,
        0b001: 1.6,
        0b010: 1.0,
        0b011: 0.67,
        0b100: 0.4,
        0b101: 0.25,
        0b110: 0.167,
        0b111: 0.1,
    }, doc="Internal reference slew rate, mV/us (Vout slew rate is 2x this if Vout_Select=1)")

# Shared base for buck 1-4 control registers (0x01, 0x04, 0x07, 0x0A)
class BuckControl(Bitfield):
    """Mode, current limit, phase, OVP and discharge control. R/W"""
    vout_limit_en = BooleanField(7, doc="Clamp max output voltage to 1.830V (FB pin voltage)")
    forced_pwm = BooleanField(6, doc="0=Auto-PFM/PWM, 1=Forced PWM")
    current_limit = MappingField(4, 2, {
        0b00: 2.0,
        0b01: 3.0,
        0b10: 4.2,
        0b11: 5.0,
    }, doc="Valley current limit, A (4.2A/5A codes are invalid for buck 3 and buck 4)")
    ovp_en = BooleanField(3, doc="Output overvoltage protection enable")
    phase_delay = MappingField(1, 2, {
        0b00: 0,
        0b01: 90,
        0b10: 180,
        0b11: 270,
    }, doc="Switching phase delay, degrees")
    discharge_en = BooleanField(0, doc="Output discharge resistor enable")

# Shared base for buck 1-4 Vout select/reference registers (0x02, 0x05, 0x08, 0x0B)
class BuckVref(Bitfield):
    """Feedback divider select and internal reference voltage. R/W"""
    vout_select = BooleanField(7,
        doc="0: FB=Vref, Vout range 0.55-1.82V. 1: FB=Vref/3 (internal 2R/R divider), "
            "Vout=3xVref, Vout range 1.65-5.46V")
    vref = ScaledField(0, 7, scale=0.01, scale_offset=55,
                       doc="Internal reference voltage, V (550mV to 1.82V, 10mV/step)")

# 0x00 Buck 1 soft-start (p.29)
@Mpm54304.at(0x00)
class Buck1SoftStart(BuckSoftStart):
    """Buck 1 soft-start delay/time. Default: Delay=1ms, Time=010"""
    pass

# 0x01 Buck 1 control (p.29)
@Mpm54304.at(0x01)
class Buck1Control(BuckControl):
    """Buck 1 mode/current limit/phase/OVP/discharge. Default: Vout_Limit_EN=1, Current_Limit=10, Phase=01"""
    pass

# 0x02 Buck 1 Vout select + reference (p.29)
@Mpm54304.at(0x02)
class Buck1Vref(BuckVref):
    """Buck 1 feedback divider and reference. Default: Vout_Select=0, Vref=1V"""
    pass

# 0x03 Buck 2 soft-start (p.29)
@Mpm54304.at(0x03)
class Buck2SoftStart(BuckSoftStart):
    """Buck 2 soft-start delay/time. Default: Delay=3ms, Time=011"""
    pass

# 0x04 Buck 2 control (p.29)
@Mpm54304.at(0x04)
class Buck2Control(BuckControl):
    """Buck 2 mode/current limit/phase/OVP/discharge. Default: Phase=10"""
    pass

# 0x05 Buck 2 Vout select + reference (p.29)
@Mpm54304.at(0x05)
class Buck2Vref(BuckVref):
    """Buck 2 feedback divider and reference. Default: Vout_Select=1, Vref=1.1V (Vout=3.3V)"""
    pass

# 0x06 Buck 3 soft-start (p.29)
@Mpm54304.at(0x06)
class Buck3SoftStart(BuckSoftStart):
    """Buck 3 soft-start delay/time. Default: Delay=1ms, Time=001"""
    pass

# 0x07 Buck 3 control (p.29)
@Mpm54304.at(0x07)
class Buck3Control(BuckControl):
    """Buck 3 mode/current limit/phase/OVP/discharge. Default: Phase=11"""
    pass

# 0x08 Buck 3 Vout select + reference (p.29)
@Mpm54304.at(0x08)
class Buck3Vref(BuckVref):
    """Buck 3 feedback divider and reference. Default: Vout_Select=1, Vref=0.6V (Vout=1.8V)"""
    pass

# 0x09 Buck 4 soft-start (p.29)
@Mpm54304.at(0x09)
class Buck4SoftStart(BuckSoftStart):
    """Buck 4 soft-start delay/time. Default: Delay=2ms, Time=001"""
    pass

# 0x0A Buck 4 control (p.29)
@Mpm54304.at(0x0A)
class Buck4Control(BuckControl):
    """Buck 4 mode/current limit/phase/OVP/discharge. Default: Phase=00"""
    pass

# 0x0B Buck 4 Vout select + reference (p.29)
@Mpm54304.at(0x0B)
class Buck4Vref(BuckVref):
    """Buck 4 feedback divider and reference. Default: Vout_Select=1, Vref~0.83V (Vout=2.5V)"""
    pass

# 0x0C System: enables + UVLO + GPIO output bit (p.29)
@Mpm54304.at(0x0C)
class SystemEnable(Bitfield):
    """Buck enables, input UVLO threshold, GPIO output-port bit. R/W"""
    en1 = BooleanField(7, doc="Buck 1 enable")
    en2 = BooleanField(6, doc="Buck 2 enable")
    en3 = BooleanField(5, doc="Buck 3 enable")
    en4 = BooleanField(4, doc="Buck 4 enable")
    uvlo = MappingField(1, 2, {
        0b00: 3.5,
        0b01: 4.5,
        0b10: 5.8,
        0b11: 8.5,
    }, doc="Input UVLO rising threshold, V")
    op_bit = BooleanField(0,
        doc="GPIO output level when pin 20 is in OP mode (0: pulled low, 1: open drain)")

# 0x0D System: switching frequency, shutdown sequencing, I2C address (p.29)
@Mpm54304.at(0x0D)
class SystemFreq(Bitfield):
    """Switching frequency, shutdown sequence, I2C slave address bits. R/W"""
    freq = MappingField(6, 2, {
        0b00: 533000,
        0b01: 800000,
        0b10: 1060000,
        0b11: 1600000,
    }, doc="Buck switching frequency, Hz (same for all four bucks)")
    shutdown_delay_en = BooleanField(5,
        doc="0: all bucks shut down together. 1: shutdown is reverse of power-on sequence")
    i2c_slave_address = Field(0, 5, doc="Sets A5:A1 of the I2C slave address (A7:A6 fixed = 11)")

# 0x0E System: GPIO function, MTP program, PG delay, parallel mode (p.29)
@Mpm54304.at(0x0E)
class SystemGpio(Bitfield):
    """GPIO pin 20 function, MTP burn trigger, PG delay, parallel mode. R/W"""
    add_pg_op_syncout = MappingField(6, 2, {
        0b00: "ADD",
        0b01: "PG",
        0b10: "OP",
        0b11: "SYNCOUT",
    }, doc="Function of GPIO pin 20")
    mtp_program = BooleanField(5,
        doc="Set 1 to burn current I2C registers into MTP; self-clears when done (~100ms)")
    pg_delay = MappingField(2, 3, {
        0b000: 0.2e-3,
        0b001: 5e-3,
        0b010: 25e-3,
        0b011: 75e-3,
        0b100: 200e-3,
    }, doc="Power-good assertion delay, s")
    parallel_2 = BooleanField(1,
        doc="Buck 3+4 parallel mode (use FB3; buck 4 I2C/MTP regs become invalid). "
            "Must be set before EN/SYNCI goes high")
    parallel_1 = BooleanField(0,
        doc="Buck 1+2 parallel mode (use FB1; buck 2 I2C/MTP regs become invalid). "
            "Must be set before EN/SYNCI goes high")

# 0x0F System: MTP configure code (p.29)
@Mpm54304.at(0x0F)
class MtpConfigCode(Bitfield):
    """MTP configuration code. R/W, default=00h (standard MPM54304)"""
    code = Field(0, 8, doc="0x00: standard MPM54304, 0x01: MPM54304-0001, etc.")

# 0x10 System: MTP revision number (p.29)
@Mpm54304.at(0x10)
class MtpRevision(Bitfield):
    """MTP table revision number. R/W"""
    revision = Field(0, 8, doc="Customer-updatable MTP revision tag")

# 0x11 System: MTP program password (p.29)
@Mpm54304.at(0x11)
class MtpProgramPassword(Bitfield):
    """Password required to unlock the MTP_Program bit. Write"""
    password = Field(0, 8, doc="MTP write-unlock password")

# 0x12 Status: power good / thermal flags (p.29)
@Mpm54304.at(0x12)
class Status(Bitfield):
    """Live power-good and thermal status. Read"""
    pg1 = BooleanField(7, doc="Buck 1 power good")
    pg2 = BooleanField(6, doc="Buck 2 power good")
    pg3 = BooleanField(5, doc="Buck 3 power good")
    pg4 = BooleanField(4, doc="Buck 4 power good")
    ot_warning = BooleanField(3, doc="Die temperature above 120C")
    ot_protection = BooleanField(2, doc="Thermal shutdown active (die temperature above 160C)")

# 0x13 System: vendor ID, checksum flag, MTP page index (p.29)
@Mpm54304.at(0x13)
class SystemStatus(Bitfield):
    """Vendor ID, MTP checksum flag, active MTP page. Read"""
    vendor_id = Field(4, 4, doc="Fixed vendor ID, always 1000b")
    checksum_flag = BooleanField(3, doc="Current MTP page failed CRC/checksum check")
    current_mtp_page_index = MappingField(0, 3, {
        0b000: "DEFAULT",
        0b001: "PAGE1",
        0b011: "PAGE3",
    }, doc="Index of the MTP page currently loaded into the I2C registers")
