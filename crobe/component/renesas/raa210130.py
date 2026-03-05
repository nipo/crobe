from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
from ...util.pretty import metric
import enum
import math

class Raa210130(i2c.AddressedSlave):
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
        super().__init__(bus, "raa210130", saddr)

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
            reg = reg.__class__
            value = int(reg)

        try:
            addr = int(reg)
        except TypeError:
            addr = self._by_class[reg]
        reg_class = self._by_addr[addr]

        pretty = reg_class(int(value))

        reg_size = reg_class._width // 8
        raw = int(value).to_bytes(reg_size, "little")

        self.logger.trace("Reg write %s (%02x): %s (%s)", reg_class.__name__, reg, pretty, raw.hex())
        super().mem_write(addr, raw)

@i2c.Interface.db.register("raa210130")
def raa_get(bus):
    return Raa210130(bus, None)

# Shared base for fault response registers (0x41, 0x45, 0x47, 0x50, 0x54, 0x56, 0x5A, 0x5C)
class FaultResponse(Bitfield):
    response = MappingField(6, 2, {0: "CONTINUE", 2: "DISABLE_RETRY"},
                            doc="Behavior on fault")
    retry = MappingField(3, 3, {0: "NO_RETRY", 7: "CONTINUOUS"},
                         doc="Retry count after fault")
    delay = ScaledField(0, 3, scale=0.025, doc="Delay before response, s")

# 0x00 PAGE (p.40)
@Raa210130.at(0x00)
class Page(Bitfield):
    """Rail selector. R/W, Bit, default=00h (Page 0)"""
    page = Field(0, 8, doc="Active rail page select")

# 0x01 OPERATION (p.41)
@Raa210130.at(0x01)
class Operation(Bitfield):
    """Enable/disable, VOUT source. R/W, Bit, default=48h (Immediate off, act on fault)"""
    output_enable = BooleanField(7, doc="Enable output voltage")
    soft_off = BooleanField(6, doc="Soft-off sequencing active")
    vout_source = MappingField(4, 2, ["COMMAND", "MARGIN_LOW", "MARGIN_HIGH", None],
                               doc="Vout setpoint source")
    margin_response = MappingField(2, 2, [None, "Ignore", "Act", None],
                                   doc="Margin fault response")

# 0x02 ON_OFF_CONFIG (p.42)
@Raa210130.at(0x02)
class OnOffConfig(Bitfield):
    """On/off configuration settings. R/W, Bit, default=16h (ENABLE pin control, active high, immediate off)"""
    enable_source = MappingField(2, 3, {
        0b000: "ALWAYS_ON",
        0b101: "ENABLE_PIN",
        0b110: "OPERATION_ONLY",
        0b111: "OPERATION_AND_PIN",
    }, doc="Source of enable")
    enable_polarity = MappingField(1, 1, {0: "ACTIVE_LOW", 1: "ACTIVE_HIGH"},
                                   doc="Polarity of ENABLE pin")
    turn_off_action = MappingField(0, 1, {0: "SOFT_OFF", 1: "IMMEDIATE"},
                                   doc="Turn-off behavior")

# 0x04 PHASE (p.43)
@Raa210130.at(0x04)
class Phase(Bitfield):
    """Phase selector. R/W, Direct, default=00h (Phase 0)"""
    phase = Field(0, 8, doc="Phase index for multi-phase")

# 0x10 WRITE_PROTECT (p.44)
@Raa210130.at(0x10)
class WriteProtect(Bitfield):
    """Write protection to sets of commands. R/W, Bit, default=00h (No write protection)"""
    write_protect = MappingField(0, 8, {
        0b00000000: "ENABLE_ALL",
        0b00000010: "EXCEPT_WP_OP_PAGE_ONOFF_VOUT_DMA",
        0b00100000: "EXCEPT_WP_OP_PAGE_ONOFF_VOUT",
        0b01000000: "EXCEPT_WP_OP_PAGE",
        0b10000000: "EXCEPT_WP",
    }, doc="Register write protection level")

# 0x19 CAPABILITY (p.45)
@Raa210130.at(0x19)
class Capability(Bitfield):
    """Reports PMBus capability. Read, Bit, default=D0h"""
    pec_support = BooleanField(7, doc="PEC supported")
    max_bus_speed = MappingField(5, 2, {
        0b00: "100KHZ", 0b01: "400KHZ", 0b10: "1MHZ", 0b11: "NOT_SUPPORTED",
    }, doc="Max SMBus clock")
    smbalert_support = BooleanField(4, doc="SMBAlert# supported")
    numeric_format = MappingField(3, 1, {0: "LINEAR_DIRECT", 1: "IEEE_HALF"},
                                  doc="Telemetry data format")

# 0x20 VOUT_MODE (p.46)
@Raa210130.at(0x20)
class VoutMode(Bitfield):
    """Defines format for output voltage related commands. Read, Bit, default=40h (Direct format)"""
    mode = MappingField(5, 3, {0: "LINEAR", 1: "VID", 2: "DIRECT"},
                        doc="Vout data format")
    exponent = Field(0, 5, doc="Linear mode exponent")

# 0x21 VOUT_COMMAND (p.47)
@Raa210130.at(0x21)
class VoutCommand(Bitfield):
    """Output voltage set by PMBus. R/W, Direct, default=0ABEh (2750mV)"""
    vout = ScaledField(0, 16, scale=0.001, doc="Output voltage setpoint, V")

# 0x22 VOUT_TRIM (p.47)
@Raa210130.at(0x22)
class VoutTrim(Bitfield):
    """Applies trim voltage to Vout set-point. R/W, Direct, default=0000h (0mV)"""
    vout_trim = ScaledField(0, 16, scale=0.001, doc="Output voltage trim, V")

# 0x23 VOUT_CAL_OFFSET (p.48)
@Raa210130.at(0x23)
class VoutCalOffset(Bitfield):
    """Applies offset voltage to Vout set-point. R/W, Direct, default=0000h (0mV)"""
    vout_cal_offset = ScaledField(0, 16, scale=0.001, doc="Output calibration offset, V")

# 0x24 VOUT_MAX (p.48)
@Raa210130.at(0x24)
class VoutMax(Bitfield):
    """Absolute maximum voltage setting. R/W, Direct, default=0BEAh (3050mV)"""
    vout_max = ScaledField(0, 16, scale=0.001, doc="Output voltage upper clamp, V")

# 0x25 VOUT_MARGIN_HIGH (p.49)
@Raa210130.at(0x25)
class VoutMarginHigh(Bitfield):
    """Sets voltage target during margin high. R/W, Direct, default=0B47h (2887mV)"""
    vout_margin_high = ScaledField(0, 16, scale=0.001, doc="Margin high setpoint, V")

# 0x26 VOUT_MARGIN_LOW (p.49)
@Raa210130.at(0x26)
class VoutMarginLow(Bitfield):
    """Sets voltage target during margin low. R/W, Direct, default=0A34h (2612mV)"""
    vout_margin_low = ScaledField(0, 16, scale=0.001, doc="Margin low setpoint, V")

# 0x27 VOUT_TRANSITION_RATE (p.50)
@Raa210130.at(0x27)
class VoutTransitionRate(Bitfield):
    """Slew rate setting for Vout ramp. R/W, Direct, default=0C8h (2mV/us)"""
    vout_transition_rate = ScaledField(0, 16, scale=10, doc="Vout slew rate, V/s")

# 0x28 VOUT_DROOP (p.50)
@Raa210130.at(0x28)
class VoutDroop(Bitfield):
    """Sets the load-line (V/I slope) resistance for the output. R/W, Direct, default=0000h (0uV/A)"""
    vout_droop = ScaledField(0, 16, scale=1e-5, doc="Adaptive voltage positioning, V/A")

# 0x2B VOUT_MIN (p.51)
@Raa210130.at(0x2B)
class VoutMin(Bitfield):
    """Absolute minimum voltage setting. R/W, Direct, default=0000h (0mV)"""
    vout_min = ScaledField(0, 16, scale=0.001, doc="Output voltage lower clamp, V")

# 0x33 FREQUENCY_SWITCH (p.51)
@Raa210130.at(0x33)
class FrequencySwitch(Bitfield):
    """Sets PWM switching frequency. R/W, Direct, default=02BCh (700kHz)"""
    frequency = ScaledField(0, 16, scale=1000, doc="Switching frequency, Hz")

# 0x34 POWER_MODE (p.52)
@Raa210130.at(0x34)
class PowerMode(Bitfield):
    """Sets the power conversion mode. R/W, Bit, default=03h (Maximum power)"""
    power_mode = MappingField(0, 8, {
        0x00: "MAX_EFFICIENCY",
        0x03: "MAX_POWER",
        0x04: "MFR_DEFINED",
    }, doc="Power conversion mode")

# 0x35 VIN_ON (p.53)
@Raa210130.at(0x35)
class VinOn(Bitfield):
    """Sets the Vin startup threshold. R/W, Direct, default=030Ch (7800mV)"""
    vin_on = ScaledField(0, 16, scale=0.01, doc="Input voltage turn-on threshold, V")

# 0x36 VIN_OFF (p.53)
@Raa210130.at(0x36)
class VinOff(Bitfield):
    """Sets the Vin shutdown threshold. R/W, Direct, default=0000h (0mV)"""
    vin_off = ScaledField(0, 16, scale=0.01, doc="Input voltage turn-off threshold, V")

# 0x40 VOUT_OV_FAULT_LIMIT (p.54)
@Raa210130.at(0x40)
class VoutOvFaultLimit(Bitfield):
    """Sets the Vout OV fault limit. R/W, Direct, default=0C1Ch (3100mV)"""
    vout_ov_fault_limit = ScaledField(0, 16, scale=0.001, doc="Vout overvoltage fault, V")

# 0x41 VOUT_OV_FAULT_RESPONSE (p.55)
@Raa210130.at(0x41)
class VoutOvFaultResponse(FaultResponse):
    """Configures the Vout OV fault response. R/W, Bit, default=84h (Latch off)"""
    pass

# 0x44 VOUT_UV_FAULT_LIMIT (p.56)
@Raa210130.at(0x44)
class VoutUvFaultLimit(Bitfield):
    """Sets the Vout UV fault limit. R/W, Direct, default=0921h (2337mV)"""
    vout_uv_fault_limit = ScaledField(0, 16, scale=0.001, doc="Vout undervoltage fault, V")

# 0x45 VOUT_UV_FAULT_RESPONSE (p.57)
@Raa210130.at(0x45)
class VoutUvFaultResponse(FaultResponse):
    """Configures the Vout UV fault response. R/W, Bit, default=84h (Latch off)"""
    pass

# 0x46 IOUT_OC_FAULT_LIMIT (p.58)
@Raa210130.at(0x46)
class IoutOcFaultLimit(Bitfield):
    """Sets the Iout OC fault limit. R/W, Direct, default=01F4h (50A)"""
    iout_oc_fault_limit = ScaledField(0, 16, scale=0.1, doc="Output overcurrent fault, A")

# 0x47 IOUT_OC_FAULT_RESPONSE (p.59)
@Raa210130.at(0x47)
class IoutOcFaultResponse(FaultResponse):
    """Configures the Iout OC fault response. R/W, Bit, default=FCh (Latch off)"""
    pass

# 0x4F OT_FAULT_LIMIT (p.60)
@Raa210130.at(0x4F)
class OtFaultLimit(Bitfield):
    """Sets the OT fault limit. R/W, Direct, default=007Dh (125degC)"""
    ot_fault_limit = Field(0, 16, doc="Overtemperature fault, degC")

# 0x50 OT_FAULT_RESPONSE (p.61)
@Raa210130.at(0x50)
class OtFaultResponse(FaultResponse):
    """Configures the OT fault response. R/W, Bit, default=BCh (Retry)"""
    pass

# 0x51 OT_WARN_LIMIT (p.62)
@Raa210130.at(0x51)
class OtWarnLimit(Bitfield):
    """Sets the OT warning limit. R/W, Direct, default=006Eh (110degC)"""
    ot_warn_limit = Field(0, 16, doc="Overtemperature warning, degC")

# 0x53 UT_FAULT_LIMIT (p.62)
@Raa210130.at(0x53)
class UtFaultLimit(Bitfield):
    """Sets the UT fault limit. R/W, Direct, default=FFD8h (-40degC)"""
    ut_fault_limit = Field(0, 16, doc="Undertemperature fault, degC")

# 0x54 UT_FAULT_RESPONSE (p.63)
@Raa210130.at(0x54)
class UtFaultResponse(FaultResponse):
    """Configures the UT fault response. R/W, Bit, default=80h (Latch off)"""
    pass

# 0x55 VIN_OV_FAULT_LIMIT (p.64)
@Raa210130.at(0x55)
class VinOvFaultLimit(Bitfield):
    """Sets the Vin OV fault limit. R/W, Direct, default=640h (16000mV)"""
    vin_ov_fault_limit = ScaledField(0, 16, scale=0.01, doc="Vin overvoltage fault, V")

# 0x56 VIN_OV_FAULT_RESPONSE (p.65)
@Raa210130.at(0x56)
class VinOvFaultResponse(FaultResponse):
    """Configures the Vin OV fault response. R/W, Bit, default=84h (Latch off)"""
    pass

# 0x57 VIN_OV_WARN_LIMIT (p.66)
@Raa210130.at(0x57)
class VinOvWarnLimit(Bitfield):
    """Sets the Vin OV warning limit. R/W, Direct, default=0708h (18V)"""
    vin_ov_warn_limit = ScaledField(0, 16, scale=0.01, doc="Vin overvoltage warning, V")

# 0x58 VIN_UV_WARN_LIMIT (p.66)
@Raa210130.at(0x58)
class VinUvWarnLimit(Bitfield):
    """Sets the Vin UV warning limit. R/W, Direct, default=0000h (0mV)"""
    vin_uv_warn_limit = ScaledField(0, 16, scale=0.01, doc="Vin undervoltage warning, V")

# 0x59 VIN_UV_FAULT_LIMIT (p.67)
@Raa210130.at(0x59)
class VinUvFaultLimit(Bitfield):
    """Sets the Vin UV fault limit. R/W, Direct, default=02D0h (7200mV)"""
    vin_uv_fault_limit = ScaledField(0, 16, scale=0.01, doc="Vin undervoltage fault, V")

# 0x5A VIN_UV_FAULT_RESPONSE (p.68)
@Raa210130.at(0x5A)
class VinUvFaultResponse(FaultResponse):
    """Configures the Vin UV fault response. R/W, Bit, default=BCh (Retry)"""
    pass

# 0x5B IIN_OC_FAULT_LIMIT (p.69)
@Raa210130.at(0x5B)
class IinOcFaultLimit(Bitfield):
    """Sets the Iin OC fault limit. R/W, Direct, default=03E8h (10A)"""
    iin_oc_fault_limit = ScaledField(0, 16, scale=0.01, doc="Input overcurrent fault, A")

# 0x5C IIN_OC_FAULT_RESPONSE (p.70)
@Raa210130.at(0x5C)
class IinOcFaultResponse(FaultResponse):
    """Configures the Iin OC fault response. R/W, Bit, default=04h (Ignore)"""
    pass

# 0x5D IIN_OC_WARN_LIMIT (p.71)
@Raa210130.at(0x5D)
class IinOcWarnLimit(Bitfield):
    """Sets the Iin OC warning limit. R/W, Direct, default=3A98h (150A)"""
    iin_oc_warn_limit = ScaledField(0, 16, scale=0.01, doc="Input overcurrent warning, A")

# 0x60 TON_DELAY (p.71)
@Raa210130.at(0x60)
class TonDelay(Bitfield):
    """Sets turn-on delay time. R/W, Direct, default=0000h (0us)"""
    ton_delay = ScaledField(0, 16, scale=1e-5, doc="Turn-on delay, s")

# 0x61 TON_RISE (p.72)
@Raa210130.at(0x61)
class TonRise(Bitfield):
    """Sets turn-on rise time. R/W, Direct, default=1388h (5000us)"""
    ton_rise = ScaledField(0, 16, scale=1e-6, doc="Turn-on rise time, s")

# 0x64 TOFF_DELAY (p.72)
@Raa210130.at(0x64)
class ToffDelay(Bitfield):
    """Sets turn-off delay time. R/W, Direct, default=0000h (0us)"""
    toff_delay = ScaledField(0, 16, scale=1e-5, doc="Turn-off delay, s")

# 0x65 TOFF_FALL (p.73)
@Raa210130.at(0x65)
class ToffFall(Bitfield):
    """Sets turn-off fall time. R/W, Direct, default=1388h (5000us)"""
    toff_fall = ScaledField(0, 16, scale=1e-6, doc="Turn-off fall time, s")

# 0x78 STATUS_BYTE (p.74)
@Raa210130.at(0x78)
class StatusByte(Bitfield):
    """First byte of STATUS_WORD. Read, Bit"""
    busy = BooleanField(7, doc="Device busy processing")
    off = BooleanField(6, doc="Output not enabled")
    vout_ov_fault = BooleanField(5, doc="Vout overvoltage fault")
    iout_oc_fault = BooleanField(4, doc="Iout overcurrent fault")
    vin_uv_fault = BooleanField(3, doc="Vin undervoltage fault")
    temperature = BooleanField(2, doc="Temperature fault or warning")
    cml = BooleanField(1, doc="Communication/logic fault")
    other = BooleanField(0, doc="Unknown fault")

# 0x79 STATUS_WORD (p.75)
@Raa210130.at(0x79)
class StatusWord(Bitfield):
    """Summary of critical faults. Read, Bit"""
    vout = BooleanField(15, doc="Vout fault or warning")
    iout = BooleanField(14, doc="Iout fault or warning")
    input = BooleanField(13, doc="Input fault or warning")
    mfr_specific = BooleanField(12, doc="Manufacturer-specific fault")
    power_good = BooleanField(11, inverted=True, doc="Output within regulation")
    busy = BooleanField(7, doc="Device busy processing")
    off = BooleanField(6, doc="Output not enabled")
    vout_ov_fault = BooleanField(5, doc="Vout overvoltage fault")
    iout_oc_fault = BooleanField(4, doc="Iout overcurrent fault")
    vin_uv_fault = BooleanField(3, doc="Vin undervoltage fault")
    temperature = BooleanField(2, doc="Temperature fault or warning")
    cml = BooleanField(1, doc="Communication/logic fault")
    other = BooleanField(0, doc="Unknown fault")

# 0x7A STATUS_VOUT (p.76)
@Raa210130.at(0x7A)
class StatusVout(Bitfield):
    """Reports Vout warnings/faults. Read, Bit"""
    vout_ov_fault = BooleanField(7, doc="Vout overvoltage fault")
    vout_uv_fault = BooleanField(4, doc="Vout undervoltage fault")
    vout_max_warning = BooleanField(3, doc="Vout above max warning")

# 0x7B STATUS_IOUT (p.77)
@Raa210130.at(0x7B)
class StatusIout(Bitfield):
    """Reports Iout warnings/faults. Read, Bit"""
    iout_oc_fault = BooleanField(7, doc="Iout overcurrent fault")
    iout_uc_fault = BooleanField(4, doc="Iout undercurrent fault")

# 0x7C STATUS_INPUT (p.78)
@Raa210130.at(0x7C)
class StatusInput(Bitfield):
    """Reports input warnings/faults. Read, Bit"""
    vin_ov_fault = BooleanField(7, doc="Vin overvoltage fault")
    vin_ov_warn = BooleanField(6, doc="Vin overvoltage warning")
    vin_uv_warn = BooleanField(5, doc="Vin undervoltage warning")
    vin_uv_fault = BooleanField(4, doc="Vin undervoltage fault")
    vin_on_off = BooleanField(3, doc="Unit off due to low Vin")
    iin_oc_fault = BooleanField(2, doc="Iin overcurrent fault")
    iin_oc_warn = BooleanField(1, doc="Iin overcurrent warning")

# 0x7D STATUS_TEMPERATURE (p.79)
@Raa210130.at(0x7D)
class StatusTemperature(Bitfield):
    """Reports temperature warnings/faults. Read, Bit"""
    ot_fault = BooleanField(7, doc="Overtemperature fault")
    ot_warn = BooleanField(6, doc="Overtemperature warning")
    ut_fault = BooleanField(4, doc="Undertemperature fault")

# 0x7E STATUS_CML (p.80)
@Raa210130.at(0x7E)
class StatusCml(Bitfield):
    """Reports communication, memory, logic errors. Read, Bit"""
    command = BooleanField(7, doc="Invalid/unsupported command")
    data = BooleanField(6, doc="Invalid/unsupported data")
    pec = BooleanField(5, doc="Packet error check failed")
    memory = BooleanField(4, doc="Memory fault detected")
    processor = BooleanField(3, doc="Processor fault detected")
    comm = BooleanField(1, doc="Other communication fault")
    logic = BooleanField(0, doc="Other memory/logic fault")

# 0x80 STATUS_MFR_SPECIFIC (p.81)
@Raa210130.at(0x80)
class StatusMfrSpecific(Bitfield):
    """Reports other specific faults. Read, Bit"""
    adcunlock = BooleanField(7, doc="ADC unlock event")
    cfp = BooleanField(5, doc="Current foldback protection fault")
    internal_temp = BooleanField(4, doc="Internal temperature fault")
    bbevent = BooleanField(3, doc="Black box event logged")
    lms = BooleanField(2, doc="Last Man Standing event")
    sps = BooleanField(1, doc="SPS overcurrent/orver temp fault")

# 0x88 READ_VIN (p.81)
@Raa210130.at(0x88)
class ReadVin(Bitfield):
    """Reports input voltage measurement. Read, Direct"""
    vin = ScaledField(0, 16, scale=0.01, doc="Input voltage, V")

# 0x89 READ_IIN (p.82)
@Raa210130.at(0x89)
class ReadIin(Bitfield):
    """Reports input current measurement. Read, Direct"""
    iin = ScaledField(0, 16, scale=0.01, doc="Input current, A")

# 0x8B READ_VOUT (p.82)
@Raa210130.at(0x8B)
class ReadVout(Bitfield):
    """Reports output voltage measurement. Read, Direct"""
    vout = ScaledField(0, 16, scale=0.001, doc="Output voltage, V")

# 0x8C READ_IOUT (p.83)
@Raa210130.at(0x8C)
class ReadIout(Bitfield):
    """Reports output current measurement. Read, Direct"""
    iout = ScaledField(0, 16, scale=0.1, doc="Output current, A")

# 0x8D READ_TEMPERATURE_1 (p.83)
@Raa210130.at(0x8D)
class ReadTemperature1(Bitfield):
    """Reports power stage temperature measurement. Read, Direct"""
    temperature = Field(0, 16, signed = True, doc="Internal temperature, degC")

# 0x8E READ_TEMPERATURE_2 (p.84)
@Raa210130.at(0x8E)
class ReadTemperature2(Bitfield):
    """Reports internal temperature measurement. Read, Direct"""
    temperature = Field(0, 16, signed = True, doc="External temperature 1, degC")

# 0x8F READ_TEMPERATURE_3 (p.84)
@Raa210130.at(0x8F)
class ReadTemperature3(Bitfield):
    """Reports TEMP pin temperature measurement. Read, Direct"""
    temperature = Field(0, 16, signed = True, doc="External temperature 2, degC")

# 0x96 READ_POUT (p.85)
@Raa210130.at(0x96)
class ReadPout(Bitfield):
    """Reports output power. Read, Direct"""
    pout = Field(0, 16, signed = True, doc="Output power, W")

# 0x97 READ_PIN (p.85)
@Raa210130.at(0x97)
class ReadPin(Bitfield):
    """Reports input power. Read, Direct"""
    pin = Field(0, 16, signed = True, doc="Input power, W")

# 0x98 PMBUS_REVISION (p.86)
@Raa210130.at(0x98)
class PmbusRevision(Bitfield):
    """Reports the PMBus revision used. Read, Bit, default=33h (P1 R1.3, P2 R1.3)"""
    part1 = MappingField(4, 4, {0: "1.0", 1: "1.1", 2: "1.2", 3: "1.3"},
                         doc="PMBus spec part 1 revision")
    part2 = MappingField(0, 4, {0: "1.0", 1: "1.1", 2: "1.2", 3: "1.3"},
                         doc="PMBus spec part 2 revision")

# 0x99 MFR_ID (p.86)
@Raa210130.at(0x99)
class MfrId(Bitfield):
    """Stores inventory information. Block R/W, Bit, default=00000000h"""
    mfr_id = Field(0, 32, doc="Manufacturer ID block")

# 0x9A MFR_MODEL (p.86)
@Raa210130.at(0x9A)
class MfrModel(Bitfield):
    """Stores inventory information. Block R/W, Bit, default=00000000h"""
    mfr_model = Field(0, 32, doc="Model number block")

# 0x9B MFR_REVISION (p.87)
@Raa210130.at(0x9B)
class MfrRevision(Bitfield):
    """Stores inventory information. Block R/W, Bit, default=00000000h"""
    mfr_revision = Field(0, 32, doc="Revision string block")

# 0x9D MFR_DATE (p.87)
@Raa210130.at(0x9D)
class MfrDate(Bitfield):
    """Stores inventory information. Block R/W, Bit, default=00000000h"""
    mfr_date = Field(0, 32, doc="Manufacturing date block")

# 0xAD IC_DEVICE_ID (p.87)
@Raa210130.at(0xAD)
class IcDeviceId(Bitfield):
    """Reports device identification information. Block Read, Bit, default=49D2B000h (RAA210130)"""
    mfr_code = Field(24, 8, doc="Manufacturer JEDEC code")
    id_high = Field(16, 8, doc="Device ID high byte")
    id_low = Field(8, 8, doc="Device ID low byte")
    reserved = Field(0, 8, doc="Reserved")

# 0xAE IC_DEVICE_REV (p.88)
@Raa210130.at(0xAE)
class IcDeviceRev(Bitfield):
    """Reports device revision information. Block Read, Bit"""
    hw_revision = Field(24, 8, doc="Hardware revision")
    fw_revision = Field(0, 8, doc="Firmware revision")

# 0xC5 DMAFIX (p.88)
@Raa210130.at(0xC5)
class Dmafix(Bitfield):
    """Fixed DMA transactions. R/W, Bit, default=0000h"""
    dmafix = Field(0, 32, doc="DMA fixed-address data")

# 0xC6 DMASEQ (p.88)
@Raa210130.at(0xC6)
class Dmaseq(Bitfield):
    """Sequential DMA transaction. R/W, Bit, default=0000h"""
    dmaseq = Field(0, 32, doc="DMA sequential data")

# 0xC7 DMAADDR (p.89)
@Raa210130.at(0xC7)
class Dmaaddr(Bitfield):
    """Sets the address for DMA transactions. R/W, Bit, default=0000h"""
    region = Field(13, 3, doc="DMA memory region select")
    address = Field(0, 13, doc="DMA address within region")

# 0xCD PEAK_OC_LIMIT (p.89)
@Raa210130.at(0xCD)
class PeakOcLimit(Bitfield):
    """Sets peak per phase OC limit. R/W, Direct, default=01F4h (50A)"""
    peak_oc_limit = ScaledField(0, 16, scale=0.1, signed = True, doc="Peak overcurrent limit, A")

# 0xCE PEAK_UC_LIMIT (p.90)
@Raa210130.at(0xCE)
class PeakUcLimit(Bitfield):
    """Sets peak per phase UC limit. R/W, Direct, default=FE0Ch (-50A)"""
    peak_uc_limit = ScaledField(0, 16, scale=0.1, signed = True, doc="Peak undercurrent limit, A")

# 0xD0 VMON_ON (p.90)
@Raa210130.at(0xD0)
class VmonOn(Bitfield):
    """Sets the VMON startup threshold. R/W, Direct, default=1C2h (4500mV)"""
    vmon_on = ScaledField(0, 16, scale=0.01, doc="Voltage monitor on threshold, V")

# 0xD1 VMON_OFF (p.91)
@Raa210130.at(0xD1)
class VmonOff(Bitfield):
    """Sets the VMON shutdown threshold. R/W, Direct, default=190h (4000mV)"""
    vmon_off = ScaledField(0, 16, scale=0.01, doc="Voltage monitor off threshold, V")

# 0xDD COMPPROP (p.92)
@Raa210130.at(0xDD)
class CompProp(Bitfield):
    """Configures proportional gain. R/W, Bit, default=D80189C4h"""
    mantissa_8p_override = Field(28, 4, doc=">8 phase mantissa override")
    exponent_8p_override = Field(25, 3, doc=">8 phase exponent override")
    mantissa_2p_override = Field(21, 4, doc="2-phase mantissa override")
    exponent_2p_override = Field(17, 3, doc="2-phase exponent override")
    mantissa_1p_override = Field(13, 4, doc="1-phase mantissa override")
    exponent_1p_override = Field(9, 3, doc="1-phase exponent override")
    fir_filter = BooleanField(8, doc="FIR filter enable for D term")
    mantissa = Field(4, 4, doc="P gain mantissa (value/8), all phases")
    exponent = Field(0, 3, doc="P gain exponent 2^(shift-3), all phases")

# 0xDE COMPINTEG (p.93)
@Raa210130.at(0xDE)
class CompInteg(Bitfield):
    """Configures integral gain. R/W, Bit, default=00A8h"""
    dcm_delay = Field(12, 4, doc="DCM gain step-down delay, 16*clkTs per step")
    dcm_gain = Field(8, 4, doc="Gain when in DCM")
    max_gain = Field(4, 4, doc="Max gain on integral movement, 2^(shift-1)")
    gain = Field(0, 4, doc="Integral gain, 2^(shift-1)")

# 0xDF COMPDIFF (p.94)
@Raa210130.at(0xDF)
class CompDiff(Bitfield):
    """Configures differential gain. R/W, Bit, default=0020h"""
    fir_filter = BooleanField(12, doc="FIR filter length")
    mantissa_1p_override = Field(8, 4, doc="1-phase mantissa override")
    exponent_1p_override = Field(6, 2, doc="1-phase exponent override")
    mantissa = Field(2, 4, doc="D gain mantissa (value/8)")
    exponent = Field(0, 2, doc="D gain exponent 2^(shift+1+P_shift)")

# 0xE0 COMPCFB (p.95)
@Raa210130.at(0xE0)
class CompCfb(Bitfield):
    """Configures AC current feedback. R/W, Bit, default=6840h"""
    highpass_filter = Field(8, 8, doc="High-pass filter coefficient for current feedback")
    droop_gain = Field(0, 8, doc="Current feedback gain, low droop cases")

# 0xE3 HS_BUS_CURRENT_SCALE (p.95)
@Raa210130.at(0xE3)
class HsBusCurrentScale(Bitfield):
    """Sets the high speed bus current scaling. R/W, Bit, default=4000h (1.0)"""
    hs_bus_current_scale = ScaledField(0, 16, scale=2**-14, doc="High-side bus current scale factor")

# 0xE4 PHASE_CURRENT (p.96)
@Raa210130.at(0xE4)
class PhaseCurrent(Bitfield):
    """Reports per-phase current. Read, Direct"""
    phase_current = ScaledField(0, 16, scale=0.1, signed = True, doc="Per-phase current, A")

# 0xE5 PHASE_TEMPERATURE (p.96)
@Raa210130.at(0xE5)
class PhaseTemperature(Bitfield):
    """Reports per-phase temperature. Read, Direct"""
    phase_temperature = Field(0, 16, signed = True, doc="Per-phase temperature, degC")

# 0xE9 PEAK_OCUC_COUNT (p.97)
@Raa210130.at(0xE9)
class PeakOcucCount(Bitfield):
    """Sets the count limit before fault. R/W, Bit, default=606h (6 cycles for OC & UC)"""
    uc_count = Field(8, 8, doc="Peak undercurrent event count")
    oc_count = Field(0, 8, doc="Peak overcurrent event count")

# 0xEA SLOW_IOUT_OC_LIMIT (p.98)
@Raa210130.at(0xEA)
class SlowIoutOcLimit(Bitfield):
    """Sets the slow Iout OC limit. R/W, Direct, default=01F4h (50A)"""
    slow_iout_oc_limit = ScaledField(0, 16, scale=0.1, signed = True, doc="Slow overcurrent limit, A")

# 0xEB FAST_OC_FILT_COUNT (p.98)
@Raa210130.at(0xEB)
class FastOcFiltCount(Bitfield):
    """Configures the fast OC filter. R/W, Bit, default=0696h (Filter=10.7us, Delay=100us)"""
    filter = Log2Field(8, 4, log_offset=1, offset=0, step=166.7e-9, doc="Fast OC filter coefficient, sec")
    delay = ScaledField(0, 8, scale=667e-12, doc="Fast OC blanking delay, sec")

# 0xEC SLOW_OC_FILT_COUNT (p.99)
@Raa210130.at(0xEC)
class SlowOcFiltCount(Bitfield):
    """Configures the slow OC filter. R/W, Bit, default=0606h (Filter=10.7us, Delay=1024us)"""
    filter = Log2Field(8, 4, log_offset=1, offset=0, step=166.7e-9, doc="Slow OC filter coefficient, sec")
    delay = ScaledField(0, 8, scale=170.7e-6, doc="Slow OC blanking delay, sec")

# 0xF0 LOOPCFG (p.100)
@Raa210130.at(0xF0)
class LoopCfg(Bitfield):
    """Defines rail operating configuration. R/W, Bit, default=002371B6h"""
    min_phase_count = Field(8, 4, doc="Minimum active phase count")
    all = Field(0, 32)

# 0xF2 RESTORE_CFG (p.101)
@Raa210130.at(0xF2)
class RestoreCfg(Bitfield):
    """Identifies configuration to be restored from NVM. R/W, Bit, default=00h"""
    config = Field(0, 4, doc="User configuration ID to restore, 0-15")
