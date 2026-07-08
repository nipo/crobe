from ...protocol import spi
from ...bitfield import *
from ...util.timeout import TimeoutError as TransportTimeoutError
import time


@spi.Target.db.register("adc12qj1600")
class Adc12qj1600(spi.Target):
    """TI ADC12xJ1600 family: quad/dual/single 12-bit 1.6GSPS ADC with JESD204C.

    SPI protocol: 24-bit frames, MSB first.
      Byte 0: [R/W | A14..A8]
      Byte 1: [A7..A0]
      Byte 2: [D7..D0]  (first data byte; streaming extends with additional bytes)
    Multi-byte registers are little-endian (LSB at lowest address, per datasheet).
    """

    _by_addr = {}
    _by_class = {}

    @classmethod
    def at(cls, address):
        def _dec(reg_class):
            cls._by_addr[address] = reg_class
            cls._by_class[reg_class] = address
            setattr(cls, reg_class.__name__, reg_class)
            return reg_class
        return _dec

    @classmethod
    def registers(cls):
        """Yield (address, reg_class) for every known register, sorted by address."""
        return sorted(cls._by_addr.items())

    @classmethod
    def find_reg_addr(cls, x):
        """Resolve a register address from a numeric string or name.

        Accepts hex/decimal integers (0x000C, 12) and register names in any
        capitalisation style: VendorId, VENDOR_ID, vendor_id.
        Raises ValueError if the name is not found (compatible with Click type=).
        """
        try:
            return int(x, 0)
        except (ValueError, TypeError):
            pass
        key = x.upper().replace("_", "")
        for reg_class, addr in cls._by_class.items():
            if reg_class.__name__.upper().replace("_", "") == key:
                return addr
        raise ValueError(f"unknown register: {x!r}")

    def __init__(self, port, cs=0):
        super().__init__(port, "adc12qj1600", cs)

    def _cmd(self, read, addr):
        rw = 0x80 if read else 0x00
        return bytes([rw | ((addr >> 8) & 0x7F), addr & 0xFF])

    def reg_read(self, reg):
        try:
            addr = int(reg)
        except TypeError:
            addr = self._by_class[reg]
        reg_class = self._by_addr[addr]
        n = (reg_class._width + 7) // 8
        miso = self.transaction(self._cmd(True, addr) + bytes(n))
        value = int.from_bytes(miso[2:], "little")
        result = reg_class(value)
        self.logger.debug("R 0x%03x %-20s %s", addr, reg_class.__name__, result)
        return result

    def reg_write(self, reg, value=None):
        if value is None:
            if not isinstance(reg, Bitfield):
                raise TypeError(f"reg_write: reg must be a Bitfield instance when value is omitted, got {type(reg).__name__}")
            value = int(reg)
            reg = reg.__class__
        else:
            if not isinstance(reg, int) and not (isinstance(reg, type) and issubclass(reg, Bitfield)):
                raise TypeError(f"reg_write: reg must be a Bitfield subclass or int address, got {type(reg).__name__}")
        try:
            addr = int(reg)
        except TypeError:
            addr = self._by_class[reg]
        reg_class = self._by_addr[addr]
        n = (reg_class._width + 7) // 8
        data = int(value).to_bytes(n, "little")
        self.logger.debug("W 0x%03x %-20s %s", addr, reg_class.__name__, reg_class(value))
        self.transaction(self._cmd(False, addr) + data, read_miso=False)

    # --- High-level operations (section 8.3 initialization sequence) ---

    def soft_reset(self):
        cfg = ConfigA()
        cfg.soft_reset = True
        self.reg_write(cfg)
        time.sleep(1e-3)  # device needs up to 750 ns; 1 ms gives margin

    def wait_init_done(self, timeout=1.0):
        """Poll INIT_DONE (step 5). No other SPI access should precede this."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.reg_read(InitStatus).init_done
            if r:
                return
            self.logger.info(f"Polling INIT_DONE, read {r}")
            time.sleep(1e-3)
        raise TimeoutError("ADC12QJ1600: INIT_DONE not set")

    def verify_vendor_id(self):
        vid = self.reg_read(VendorId).vendor_id
        if vid != 0x0451:
            raise ValueError(f"ADC12QJ1600: unexpected VENDOR_ID 0x{vid:04x} (expected 0x0451)")

    def set_low_power_mode(self, high_perf=True):
        """Write all four low-power registers together (step 9).
        Requires CAL_EN=0 and JESD_EN=0. Calibration must be re-run afterwards.
        """
        if high_perf:
            v1, v2, v3, v4 = 0x4B, 0x0F, 0x04, 0x1B
        else:
            v1, v2, v3, v4 = 0x46, 0x06, 0x00, 0x14  # only valid at <=1GSPS
        self.reg_write(LowPower1(low_pow_mode1=v1))
        self.reg_write(LowPower2(low_pow_mode2=v2))
        self.reg_write(LowPower3(low_pow_mode3=v3))
        self.reg_write(LowPower4(low_pow_mode4=v4))

    def configure_cpll(self, n_div, p_div=1, v_div=5, vco_bias=0x4A):
        """Configure C-PLL dividers (step 6). Must be called while CPLL_RESET=1.

        Sampling clock = CLK_freq * n_div.
        vco_bias must be 0x4A when using C-PLL (do not use the default of 0x4F).
        """
        # self.reg_write(ClkCtrl2(va11q_noisesuppr_en=True, vclk11_noisesuppr_en=True))
        self.reg_write(CpllVcoctrl1(vco_bias=vco_bias))
        self.reg_write(CpllFbdiv1(pll_p_div=p_div, pll_v_div=v_div))
        self.reg_write(CpllFbdiv2(pll_n_div=n_div))

    def wait_vco_cal_done(self, timeout=2.0):
        """Poll VCO_CAL_DONE (step 15)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.reg_read(VcoCalStatus).vco_cal_done
            if r:
                return
            self.logger.info(f"Polling VCO_CAL_DONE, read {r}")
            time.sleep(3e-3)
        raise TimeoutError("ADC12QJ1600: VCO calibration timed out")

    def wait_cpll_locked(self, timeout=10.0, stable_count=5):
        """Poll CPLL_LOCKED in JESD_STATUS (step 15).

        Requires stable_count consecutive locked reads before returning, to
        confirm the PLL is stable and not momentarily satisfying the lock condition.
        """
        deadline = time.time() + timeout
        consecutive = 0
        while time.time() < deadline:
            try:
                r = self.reg_read(JesdStatus).cpll_locked
            except TransportTimeoutError:
                self.logger.debug("Transport timeout during CPLL_LOCKED poll, retrying")
                consecutive = 0
                time.sleep(3e-3)
                continue
            if r:
                consecutive += 1
                if consecutive >= stable_count:
                    print(f"Locked. S-PLL locked flag: {self.reg_read(JesdStatus).spll_locked}")
                    self.reg_read(JesdStatus).dump_pretty(self.logger.debug)
                    self.reg_read(CpllVcoctrl1).dump_pretty(self.logger.debug)
                    self.reg_read(CpllReset).dump_pretty(self.logger.debug)
                    return
            else:
                if consecutive > 0:
                    self.logger.info(f"CPLL_LOCKED dropped after {consecutive} consecutive reads, retrying")
                consecutive = 0
                self.logger.info(f"Polling CPLL_LOCKED, read {r}")
            time.sleep(3e-3)
        raise TimeoutError("ADC12QJ1600: C-PLL did not lock")

    def trigger_calibration(self):
        """Software-trigger foreground calibration via CAL_SOFT_TRIG (step 19).
        CAL_TRIG_EN must be 0 (software trigger mode, default).
        """
        trig = CalSoftTrig()
        trig.cal_soft_trig = False
        self.reg_write(trig)
        trig.cal_soft_trig = True
        self.reg_write(trig)

    def initialize(self, n_div, jmode, p_div=1, v_div=5, km1=31, sync_sel=2, low_power_mode=False,
                   cal_cfg0=0x01, cal_cfg1=0x01, trigout_ctrl=0, cpll_ovr = False, pll_en = False,
                   pllref_se = False, div_orc = 0, div_ord = 0, jtest='disabled', ch_en=0x03):
        """Full initialization sequence (section 8.3, steps 1–19).

        Ends with trigger_calibration() (step 19). SPI reads time out in the same
        transport context after the trigger while writes still succeed — the caller
        must call wait_fg_done() on a fresh SPI context after this returns.
        """

        self.soft_reset()                                                # steps 1-4 (software)
        self.logger.info("Waiting for INIT_DONE...")
        self.wait_init_done()                                            # step 5
        self.logger.info("Steps 1-5 done...")

        # All ALM_STATUS bits default to 1 after soft-reset, clear them
        self.clear_alarms()

        if cpll_ovr:
            self.reg_write(CpllOvr(cpll_ovr_en = cpll_ovr, cpll_en_ovr_value = pll_en, cpllref_se_ovr_val = pllref_se, divref_c_mode = div_orc, divref_d_mode = div_ord))

        self.logger.info("Configuring C-PLL...")
        self.reg_write(CpllReset(cpll_reset=True))                       # step 6a
        self.configure_cpll(n_div, p_div=p_div, v_div=v_div)            # steps 6b-d
        self.reg_write(VcoCalCtrl(vco_cal_en=True))                      # step 6e
        self.reg_write(CpllReset(cpll_reset=False))                      # step 6f
        self.logger.info("Step 6 done...")

        self.reg_write(JesdEn(jesd_en=False))                            # step 7
        self.logger.info("Step 7 done...")
        self.reg_write(CalEn(cal_en=False))                              # step 8
        self.logger.info("Step 8 done...")

        self.reg_write(ChEn(ch_en))                                      # enable/disable channels A,B,C,D
        
        if low_power_mode:                                               # step 9
            self.set_low_power_mode(high_perf=False)
            self.logger.info("Step 9 done...")
        self.logger.info("Step 9 skipped...")

        self.reg_write(Jmode(jmode=jmode))                               # step 10
        self.logger.info("Step 10 done...")
        self.reg_write(Km1(km1=km1))                                     # step 11
        self.logger.info("Step 11 done...")
        self.reg_write(Jctrl(sync_sel=sync_sel))                         # step 12
        self.logger.info("Step 12 done...")

        self.reg_write(CalCfg0, cal_cfg0)                                # step 13
        self.reg_write(CalCfg1, cal_cfg1)                               

        self.reg_write(TrigoutCtrl(trigout_en = False))
        new = TrigoutCtrl(trigout_ctrl)
        self.reg_write(TrigoutCtrl(trigout_en = False, trigout=new.trigout))# step 14
        time.sleep(0.001)
        self.reg_write(TrigoutCtrl(trigout_en = new.trigout_en, trigout=new.trigout))# step 14
        
        self.logger.info("Waiting for VCO calibration...")
        self.wait_vco_cal_done()                                         # step 15
        self.logger.info("VCO calibration done. Waiting for C-PLL lock...")
        self.wait_cpll_locked()                                          # step 15
        self.logger.info("C-PLL locked")

        if jtest != 'disabled':
            self.logger.info("Setting JTEST to", jtest)
            self.reg_write(Jtest(jtest=jtest))                            # Configure test mode

        self.reg_write(CalEn(cal_en=True))                               # step 16
        self.reg_write(JesdEn(jesd_en=True))                             # step 18
        self.clear_alarms() # It is recommended that the user clears the alarms after setting JESD_EN=1
        self.logger.info("Calibration enabled, JESD enabled, alarms cleared")

        self.logger.info("Triggering foreground calibration...")
        self.trigger_calibration()                                       # step 19

    def wait_fg_done(self, timeout=5.0):
        """Poll FG_DONE in CAL_STATUS (step 21)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = self.reg_read(CalStatus).fg_done
            if r:
                return
            self.logger.info(f"Polling FG_DONE, read {r}. (cpll_locked is {self.reg_read(JesdStatus).cpll_locked})")
            time.sleep(10e-3)
        raise TimeoutError("ADC12QJ1600: foreground calibration timed out")

    def dump_status(self):
        vco  = self.reg_read(VcoCalStatus)
        jesd = self.reg_read(JesdStatus)
        cal  = self.reg_read(CalStatus)
        alm  = self.reg_read(AlmStatus)
        init = self.reg_read(InitStatus)
        vco.dump_pretty(print)
        jesd.dump_pretty(print)
        cal.dump_pretty(print)
        alm.dump_pretty(print)
        init.dump_pretty(print)
        
    def clear_alarms(self):
        """Clear all latched alarm bits (write-1-to-clear)."""
        self.reg_write(AlmStatus(0xFF))

# --- SPI Interface Control ---

@Adc12qj1600.at(0x000)
class ConfigA(Bitfield):
    DEFAULT = 0x30
    soft_reset = BooleanField(7, doc="Self-clearing; triggers a full chip reset")
    ascend     = BooleanField(5, doc="1=address increments on streaming (default), 0=decrements")
    sdo_active = BooleanField(4, doc="[RO] always reads 1")

@Adc12qj1600.at(0x002)
class DeviceConfig(Bitfield):
    DEFAULT = 0x00
    mode = MappingField(0, 2, {0: "normal", 3: "power_down"}, doc="Chip operating mode")

@Adc12qj1600.at(0x00C)
class VendorId(Bitfield):
    all       = Field(0, 16, doc="Raw 16-bit register value")
    vendor_id = Field(0, 16, doc="0x0451 for TI")

@Adc12qj1600.at(0x010)
class Usr0(Bitfield):
    DEFAULT = 0x00
    addr_hold = BooleanField(0, doc="1=address stays constant during streaming")


# --- Clock Control ---

@Adc12qj1600.at(0x029)
class ClkCtrl0(Bitfield):
    DEFAULT = 0x80
    sysref_proc_en = BooleanField(6, doc="Enable SYSREF processing and capture")
    sysref_recv_en = BooleanField(5, doc="Enable SYSREF receiver")
    sysref_zoom    = BooleanField(4, doc="Enable fine-resolution SYSREF position capture")
    sysref_sel     = Field(0, 4, doc="SYSREF source and divider selection")

@Adc12qj1600.at(0x02A)
class ClkCtrl1(Bitfield):
    DEFAULT = 0x00
    devclk_lvpecl_en = BooleanField(2, doc="Activate low voltage PECL mode for DEVCLK. Enable LVPECL termination on DEVCLK input")
    sysref_lvpecl_en = BooleanField(1, doc="Activate low voltage PECL mode for SYSREF. Enable LVPECL termination on SYSREF input")
    sysref_inverted  = BooleanField(0, doc="Invert SYSREF polarity before processing")

@Adc12qj1600.at(0x02B)
class ClkCtrl2(Bitfield):
    DEFAULT = 0x10
    va11q_noisesuppr_en  = BooleanField(2, doc="Enable noise suppression on VA11Q analog supply")
    vclk11_noisesuppr_en = BooleanField(0, doc="Enable noise suppression on VCLK11 clock supply")

@Adc12qj1600.at(0x02C)
class SysrefPos(Bitfield):
    all        = Field(0, 24, doc="Raw 24-bit register value")
    sysref_pos = Field(0, 24, doc="[RO] SYSREF capture position within DEVCLK period")


# --- ADC Control ---

@Adc12qj1600.at(0x030)
class FsRange(Bitfield):
    DEFAULT = 0xA000
    all      = Field(0, 16, doc="Raw 16-bit register value")
    fs_range = Field(0, 16, doc="Full-scale input range: 0x2000=500mVpp, 0xA000=800mVpp (default), 0xFFFF=1000mVpp")

@Adc12qj1600.at(0x037)
class LowPower1(Bitfield):
    DEFAULT = 0x4B
    low_pow_mode1 = MappingField(0, 8, {0x4B: "high_perf", 0x46: "low_power"},
                                 doc="Low-power mode byte 1; low_power only valid at <=1GSPS")

@Adc12qj1600.at(0x03B)
class TmstpCtrl(Bitfield):
    DEFAULT = 0x00
    tmstp_lvpecl_en = BooleanField(1, doc="Enable LVPECL termination on TMSTP input")
    tmstp_recv_en   = BooleanField(0, doc="Enable timestamp receiver")


# --- C-PLL ---

@Adc12qj1600.at(0x03C)
class PllrefoCtrl(Bitfield):
    DEFAULT = 0x01
    pllrefo_en = BooleanField(0, doc="Enable C-PLL reference clock output (PLLREFO pin)")

@Adc12qj1600.at(0x03D)
class CpllFbdiv1(Bitfield):
    DEFAULT = 0x00
    pll_p_div = MappingField(2, 2, {0: 1, 1: 2, 2: 4},    doc="C-PLL prescaler divide ratio")
    pll_v_div = MappingField(0, 2, {0: 5, 1: 4, 2: 3},    doc="C-PLL VCO output divide ratio")

@Adc12qj1600.at(0x03E)
class CpllFbdiv2(Bitfield):
    DEFAULT  = 0x20
    pll_n_div = Field(0, 6, doc="C-PLL feedback integer divide ratio; range 1-63, default=32")

@Adc12qj1600.at(0x03F)
class CpllVcoctrl1(Bitfield):
    DEFAULT = 0x4F
    vco_bias = Field(0, 7, doc="C-PLL VCO bias; must be 0x4A when using C-PLL")

@Adc12qj1600.at(0x048)
class SerPe(Bitfield):
    DEFAULT = 0x00
    ser_pe   = Field(0, 4, doc="Pre-emphasis level for all SerDes output lanes")

@Adc12qj1600.at(0x057)
class TrigoutCtrl(Bitfield):
    DEFAULT   = 0x00
    trigout_en = BooleanField(7, doc="Enable TRIGOUT pin output")
    trigout    = MappingField(0, 3, {0: "16UI", 1: "32UI", 2: "64UI", 3: "tmstp"},
                              doc="TRIGOUT pulse width or source: UI counts or timestamp mode")

@Adc12qj1600.at(0x058)
class CpllOvr(Bitfield):
    DEFAULT      = 0x00
    cpll_ovr_en   = BooleanField(7, doc="Enable C-PLL manual override")
    divref_d_mode = MappingField(4, 2, {0: "off", 1: "div1", 2: "div2", 3: "div4"},
                                      doc="DIVREF_D clock output divide mode")
    divref_c_mode      = MappingField(2, 2, {0: "off", 1: "div1", 2: "div2", 3: "div4"},
                                      doc="DIVREF_C clock output divide mode")
    cpllref_se_ovr_val = BooleanField(1, doc="Override value for C-PLL reference single-ended input")
    cpll_en_ovr_value  = BooleanField(0, doc="Override value for C-PLL enable signal")

@Adc12qj1600.at(0x059)
class VcoFreqTrim(Bitfield):
    vco_freq_trim = Field(0, 7, doc="VCO frequency trim; written automatically by the VCO calibration engine")

@Adc12qj1600.at(0x05C)
class CpllReset(Bitfield):
    DEFAULT   = 0x00
    cpll_reset = BooleanField(0, doc="Assert (1) before changing PLL parameters; deassert (0) to start locking")

@Adc12qj1600.at(0x05D)
class VcoCalCtrl(Bitfield):
    DEFAULT = 0x40 
    vco_cal_stl = Field(4, 3, doc="VCO calibration settling time factor; default=4")
    vco_cal_en  = BooleanField(0, doc="Enable VCO calibration engine")

@Adc12qj1600.at(0x05E)
class VcoCalStatus(Bitfield):
    vco_cal_done = BooleanField(0, doc="[RO] set when VCO calibration completes")


# --- Calibration ---

@Adc12qj1600.at(0x061)
class CalEn(Bitfield): 
    DEFAULT = 0x01
    cal_en   = BooleanField(0, doc="Set (1) to run calibration; clear (0) to hold in reset for reconfiguration")

@Adc12qj1600.at(0x062)
class CalCfg0(Bitfield):
    DEFAULT = 0x01
    cal_bgos = BooleanField(3, doc="Enable background offset calibration")
    cal_os   = BooleanField(2, doc="Enable foreground offset calibration")
    cal_bg   = BooleanField(1, doc="Enable background linearity calibration")
    cal_fg   = BooleanField(0, doc="Enable foreground linearity calibration (default enabled)")

@Adc12qj1600.at(0x065)
class CalCfg1(Bitfield):
    DEFAULT = 0x01
    osref    = BooleanField(2, doc="0=mid-code reference (AC-coupled), 1=spare ADC reference (DC-coupled, requires CAL_BG=1)")

@Adc12qj1600.at(0x068)
class CalAvg(Bitfield):
    DEFAULT = 0x61
    os_avg   = Field(4, 3, doc="Offset correction averaging exponent; default=6")
    cal_avg  = Field(0, 3, doc="Linearity calibration averaging exponent; default=1")

@Adc12qj1600.at(0x06A)
class CalStatus(Bitfield):
    cal_stat    = Field(2, 3, doc="[RO] calibration state machine code")
    cal_stopped = BooleanField(1, doc="[RO] set when calibration engine is halted")
    fg_done     = BooleanField(0, doc="[RO] set when foreground calibration completes")

@Adc12qj1600.at(0x06B)
class CalPinCfg(Bitfield):
    DEFAULT       = 0x00
    cal_status_sel = MappingField(1, 2, {0: "fg_done", 1: "cal_stopped", 2: "alarm", 3: "low"},
                                  doc="Signal driven on the CAL_STATUS output pin")
    cal_trig_en = BooleanField(0, doc="0=software trigger via CAL_SOFT_TRIG, 1=hardware CALTRIG pin")

@Adc12qj1600.at(0x06C)
class CalSoftTrig(Bitfield):
    DEFAULT      = 0x01
    cal_soft_trig = BooleanField(0, doc="Toggle 0→1 to software-trigger a calibration cycle")

@Adc12qj1600.at(0x06E)
class CalLp(Bitfield):
    DEFAULT     = 0x88
    lp_sleep_dly = Field(5, 3, doc="Low-power sleep delay before powering down")
    lp_wake_dly  = Field(3, 2, doc="Low-power wake delay before resuming conversion")
    lp_trig      = BooleanField(1, doc="Trigger entry into low-power calibration state")
    lp_en        = BooleanField(0, doc="Enable low-power calibration mode")


# --- Trim (factory values loaded from Fuse ROM; normally left at reset values) ---

@Adc12qj1600.at(0x07A)
class GainTrim(Bitfield):
    gain_trim = Field(0, 8, doc="Factory gain trim; do not modify")

@Adc12qj1600.at(0x07C)
class BgTrim(Bitfield):
    bg_trim = Field(0, 4, doc="Factory bandgap voltage trim; do not modify")

@Adc12qj1600.at(0x07E)
class RtrimA(Bitfield):
    rtrim_a = Field(0, 8, doc="Factory resistor trim A; do not modify")

@Adc12qj1600.at(0x07F)
class RtrimB(Bitfield):
    rtrim_b = Field(0, 8, doc="Factory resistor trim B; do not modify")

@Adc12qj1600.at(0x080)
class RtrimC(Bitfield):
    rtrim_c = Field(0, 8, doc="Factory resistor trim C; do not modify")

@Adc12qj1600.at(0x081)
class RtrimD(Bitfield):
    rtrim_d = Field(0, 8, doc="Factory resistor trim D; do not modify")

@Adc12qj1600.at(0x09A)
class AdcSrcDly(Bitfield):
    DEFAULT    = 0x08
    adc_src_dly = Field(0, 5, doc="ADC source delay; range 0-31, default=8; only change when CAL_EN=0")

@Adc12qj1600.at(0x09B)
class MuxSelDly(Bitfield):
    DEFAULT    = 0x07
    mux_sel_dly = Field(0, 5, doc="Mux select delay; range 0-31, default=7")

@Adc12qj1600.at(0x09D)
class AdcDith(Bitfield):
    adc_dith_err = BooleanField(2, doc="Enable dither error correction path")
    adc_dith_amp = BooleanField(1, doc="0=small dither amplitude (better SNR), 1=large (better spurious)")
    adc_dith_en  = BooleanField(0, doc="Enable ADC input dithering")


# --- Timestamp ---

@Adc12qj1600.at(0x160)
class LsbCtrl(Bitfield):
    DEFAULT      = 0x00
    time_stamp_en = BooleanField(0, doc="Replace ADC output LSB with a TMSTP edge timestamp bit")


# --- JESD204C ---

@Adc12qj1600.at(0x200)
class JesdEn(Bitfield):
    DEFAULT = 0x01
    jesd_en  = BooleanField(0, doc="Enable JESD204C link; set after CAL_EN=1, clear before reconfiguring JESD registers")

@Adc12qj1600.at(0x201)
class Jmode(Bitfield):
    DEFAULT = 0x00
    jmode    = Field(0, 6, doc="JESD204C output mode index; only change when JESD_EN=0 and CAL_EN=0")

@Adc12qj1600.at(0x202)
class Km1(Bitfield):
    DEFAULT = 0x1F
    km1      = Field(0, 8, doc="K minus 1: frames per multiframe; ignored in 64B/66B modes")

@Adc12qj1600.at(0x203)
class JsyncN(Bitfield):
    DEFAULT = 0x01
    jsync_n  = BooleanField(0, doc="0=assert sync request (software equivalent of driving SYNC~ pin low)")

@Adc12qj1600.at(0x204)
class Jctrl(Bitfield):
    DEFAULT  = 0x03
    alt_lanes = BooleanField(4, doc="Enable alternate lane mapping")
    sync_sel  = MappingField(2, 2, {0: "syncse", 1: "tmstp", 2: "software"},
                             doc="SYNC input source")
    sformat   = MappingField(1, 1, {0: "offset_binary", 1: "twos_complement"},
                             doc="Output sample format")
    scr       = BooleanField(0, doc="Enable 8B/10B scrambler; always active in 64B/66B mode")

@Adc12qj1600.at(0x205)
class Jtest(Bitfield):
    DEFAULT = 0x00
    jtest = MappingField(0, 5, 
                         {0: "disabled", 1: "PRBS7", 2: "PRBS15",
                          3: "PRBS23", 4: "ramp", 5: "transport",
                          6: "D21.5", 7: "K28.5", 8: "repeated_ILA",
                          9: "modified_RPAT", 10: "serial_low", 11: "serial_high",
                          13: "PRBS9", 14: "PRBS31", 15: "clock_test", 17: "K28.7"},
                         doc="SerDes output test pattern")

@Adc12qj1600.at(0x206)
class Did(Bitfield):
    DEFAULT = 0x00
    did = Field(0, 8, doc="Device identification code transmitted in JESD204C ILA sequence")

@Adc12qj1600.at(0x207)
class Fchar(Bitfield):
    DEFAULT = 0x00
    fchar = MappingField(0, 2, {0: "K28.7", 1: "K28.1", 2: "K28.5"},
                         doc="8B/10B frame character used for alignment")

@Adc12qj1600.at(0x208)
class JesdStatus(Bitfield):
    link_up     = BooleanField(6, doc="[RO] JESD204C link is fully established")
    sync_status = BooleanField(5, doc="[RO] 0=SYNC~ asserted; 1=SYNC~ de-asserted")
    realigned   = BooleanField(4, doc="[RO] SYSREF caused a lane re-alignment")
    aligned     = BooleanField(3, doc="[RO] LMFC phase established by SYSREF")
    spll_locked = BooleanField(2, doc="[RO] SerDes S-PLL is locked")
    cpll_locked = BooleanField(0, doc="[RO] converter C-PLL is locked")

@Adc12qj1600.at(0x209)
class ChEn(Bitfield):
    DEFAULT     = 0x03
    single_ch_en = BooleanField(2, doc="Enable single-channel (bypass interleaving) mode")
    cd_en        = BooleanField(1, doc="Enable channel CD pair (ADC2/ADC3)")
    ab_en        = BooleanField(0, doc="Enable channel AB pair (ADC0/ADC1)")

@Adc12qj1600.at(0x20F)
class Shmode(Bitfield):
    shmode = MappingField(0, 2, {0: "crc12", 2: "fec"},
                          doc="64B/66B sync-header mode: CRC-12 or forward error correction")

@Adc12qj1600.at(0x210)
class SyncThresh(Bitfield):
    DEFAULT    = 0x03
    sync_thresh = Field(0, 5, doc="Number of valid K28.5 characters required before declaring alignment")


# --- Over-range ---

@Adc12qj1600.at(0x211)
class OvrTh(Bitfield):
    DEFAULT = 0xF2
    ovr_th   = Field(0, 8, doc="Over-range detection threshold; level = 20·log10(ovr_th/256) dBFS(peak), default=0xF2 (≈-0.5dBFS)")

@Adc12qj1600.at(0x213)
class OvrCfg(Bitfield):
    DEFAULT = 0x07
    ovr_en   = BooleanField(3, doc="Enable over-range detection")
    ovr_n    = Field(0, 3,    doc="Over-range pulse extension; minimum flag duration = 4·2^ovr_n samples")


# --- Status / Alarms ---

@Adc12qj1600.at(0x270)
class InitStatus(Bitfield):
    init_done = BooleanField(0, doc="[RO] poll until 1 after power-on before any further SPI access")

@Adc12qj1600.at(0x29A)
class LowPower2(Bitfield):
    low_pow_mode2 = MappingField(0, 8, {0x0F: "high_perf", 0x06: "low_power"},
                                 doc="Low-power mode byte 2")

@Adc12qj1600.at(0x29B)
class LowPower3(Bitfield):
    low_pow_mode3 = MappingField(0, 8, {0x04: "high_perf", 0x00: "low_power"},
                                 doc="Low-power mode byte 3")

@Adc12qj1600.at(0x29C)
class LowPower4(Bitfield):
    low_pow_mode4 = MappingField(0, 8, {0x1B: "high_perf", 0x14: "low_power"},
                                 doc="Low-power mode byte 4")

@Adc12qj1600.at(0x2C0)
class Alarm(Bitfield):
    alarm = BooleanField(0, doc="[RO] 1 if any unmasked ALM_STATUS bit is set")

@Adc12qj1600.at(0x2C1)
class AlmStatus(Bitfield):
    DEFAULT      = 0x3F
    fifo_alm      = BooleanField(5, doc="JESD204C FIFO overflow or underflow alarm")
    spll_alm      = BooleanField(4, doc="SerDes S-PLL loss-of-lock alarm")
    link_alm      = BooleanField(3, doc="JESD204C link error alarm")
    realigned_alm = BooleanField(2, doc="Unexpected SYSREF re-alignment alarm")
    clk_alm       = BooleanField(0, doc="Device clock loss-of-signal alarm")

@Adc12qj1600.at(0x2C2)
class AlmMask(Bitfield):
    DEFAULT           = 0x3F
    mask_fifo_alm      = BooleanField(5, doc="Mask FIFO alarm from ALARM pin and ALARM register")
    mask_pll_alm       = BooleanField(4, doc="Mask S-PLL alarm from ALARM pin and ALARM register")
    mask_link_alm      = BooleanField(3, doc="Mask link alarm from ALARM pin and ALARM register")
    mask_realigned_alm = BooleanField(2, doc="Mask re-alignment alarm from ALARM pin and ALARM register")
    mask_clk_alm       = BooleanField(0, doc="Mask clock alarm from ALARM pin and ALARM register")

@Adc12qj1600.at(0x2C4)
class FifoLaneAlm(Bitfield):
    DEFAULT      = 0xFF
    fifo_lane_alm = Field(0, 8, doc="Per-lane FIFO alarm bitmap; one bit per active JESD lane")


# --- Per-channel offset trim (16-bit; bits 15:12 reserved) ---

class _OfsBase(Bitfield):
    all = Field(0, 16, doc="Raw 16-bit register value")
    ofs = Field(0, 12, doc="12-bit unsigned offset correction value; bits 15:12 are reserved")

@Adc12qj1600.at(0x330)
class Ofs0(_OfsBase):   # ADC0
    pass

@Adc12qj1600.at(0x332)
class Ofs1(_OfsBase):   # ADC1
    pass

@Adc12qj1600.at(0x334)
class Ofs2a(_OfsBase):  # ADC2 sampling INA+/-
    pass

@Adc12qj1600.at(0x336)
class Ofs2b(_OfsBase):  # ADC2 sampling INB+/-
    pass

@Adc12qj1600.at(0x338)
class Ofs3c(_OfsBase):  # ADC3 sampling INC+/-
    pass

@Adc12qj1600.at(0x33A)
class Ofs3d(_OfsBase):  # ADC3 sampling IND+/-
    pass

@Adc12qj1600.at(0x33C)
class Ofs4(_OfsBase):   # ADC4
    pass

@Adc12qj1600.at(0x33E)
class Ofs5(_OfsBase):   # ADC5
    pass


# --- Per-channel gain trim ---

class _GainBase(Bitfield):
    gain     = Field(0, 5, doc="5-bit fine gain adjustment; bits 7:5 are reserved")

@Adc12qj1600.at(0x360)
class Gain0(_GainBase):   # ADC0
    pass

@Adc12qj1600.at(0x361)
class Gain1(_GainBase):   # ADC1
    pass

@Adc12qj1600.at(0x362)
class Gain2a(_GainBase):  # ADC2 sampling INA+/-
    pass

@Adc12qj1600.at(0x363)
class Gain2b(_GainBase):  # ADC2 sampling INB+/-
    pass

@Adc12qj1600.at(0x364)
class Gain3c(_GainBase):  # ADC3 sampling INC+/-
    pass

@Adc12qj1600.at(0x365)
class Gain3d(_GainBase):  # ADC3 sampling IND+/-
    pass

@Adc12qj1600.at(0x366)
class Gain4(_GainBase):   # ADC4
    pass

@Adc12qj1600.at(0x367)
class Gain5(_GainBase):   # ADC5
    pass


def _main():
    rs = [
        ClkCtrl0(sysref_recv_en=True),
        ClkCtrl2(va11q_noisesuppr_en=True, vclk11_noisesuppr_en=True),
        AlmMask(mask_fifo_alm=False, mask_clk_alm=False)
        ]
    for r in rs:
        print(r)
        print(hex(int(r)))
        print()
    
    cfg = CpllFbdiv1(pll_p_div=4, pll_v_div=4)
    print(cfg)
    print(hex(int(cfg)))
    print()

if __name__ == "__main__":
    _main()
