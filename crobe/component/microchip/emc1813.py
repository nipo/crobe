from ...protocol import i2c
import functools
import enum

class Bytes(enum.IntEnum):
    INT_HIGH_BYTE          = 0x00
    EXT1_HIGH_BYTE         = 0x01
    STATUS                 = 0x02
    CONFIG                 = 0x03
    CONVERT                = 0x04
    INT_DIODE_HIGH_LIMIT   = 0x05
    INT_DIODE_LOW_LIMIT    = 0x06
    EXT1_HIGH_LIMIT_HB     = 0x07
    EXT1_LOW_LIMIT_HB      = 0x08
    CONFIG2                = 0x09
    CONVERT2               = 0x0A
    INT_DIODE_HIGH_LIMIT2  = 0x0B
    INT_DIODE_LOW_LIMIT2   = 0x0C
    EXT1_HIGH_LIMIT_HB2    = 0x0D
    EXT1_LOW_LIMIT_HB2     = 0x0E
    ONE_SHOT               = 0x0F
    EXT1_LOW_BYTE          = 0x10
    SCRATCHPAD1            = 0x11
    SCRATCHPAD2            = 0x12
    EXT1_HIGH_LIMIT_LB     = 0x13
    EXT1_LOW_LIMIT_LB      = 0x14
    EXT2_HIGH_LIMIT_HB     = 0x15
    EXT2_LOW_LIMIT_HB      = 0x16
    EXT2_HIGH_LIMIT_LB     = 0x17
    EXT2_LOW_LIMIT_LB      = 0x18
    EXT1_THERM_LIMIT       = 0x19
    EXT2_THERM_LIMIT       = 0x1A
    EXT_DIODE_FAULT_STATUS = 0x1B
    DIODE_FAULT_MASK       = 0x1F
    INT_DIODE_THERM_LIMIT  = 0x20
    THERM_HYSTERESIS       = 0x21
    CONSECUTIVE_ALERT      = 0x22
    EXT2_HIGH_BYTE         = 0x23
    EXT2_LOW_BYTE          = 0x24
    EXT1_BETA_CONFIG       = 0x25
    EXT2_BETA_CONFIG       = 0x26
    EXT1_IDEALITY_FACTOR   = 0x27
    EXT2_IDEALITY_FACTOR   = 0x28
    INT_LOW_BYTE           = 0x29
    EXT3_HIGH_BYTE         = 0x2A
    EXT3_LOW_BYTE          = 0x2B
    EXT3_HIGH_LIMIT_HB     = 0x2C
    EXT3_LOW_LIMIT_HB      = 0x2D
    EXT3_HIGH_LIMIT_LB     = 0x2E
    EXT3_LOW_LIMIT_LB      = 0x2F
    EXT3_THERM_LIMIT       = 0x30
    EXT3_IDEALITY_FACTOR   = 0x31
    HIGH_LIMIT_STATUS      = 0x3A
    LOW_LIMIT_STATUS       = 0x3B
    THERM_LIMIT_STATUS     = 0x3C
    ROC_GAIN               = 0x3D
    ROC_CONFIG             = 0x3E
    ROC_STATUS             = 0x3F
    R1_RESH                = 0x40
    R1_LIMH                = 0x41
    R1_LIML                = 0x42
    R1_SMPL                = 0x43
    R2_RESH                = 0x44
    R2_3_RESL              = 0x45
    R2_LIMH                = 0x46
    R2_LIML                = 0x47
    R2_SMPL                = 0x48
    PER_MAXTH              = 0x49
    PER_MAXT1L             = 0x4A
    PER_MAXTH2             = 0x4B
    PER_MAXT2_3L           = 0x4C
    GBL_MAXT1H             = 0x4D
    GBL_MAXT1L             = 0x4E
    GBL_MAXT2H             = 0x4F
    GBL_MAXT2L             = 0x50
    FILTER_SEL             = 0x51
    INT_HIGH_BYTE2         = 0x60
    INT_LOW_BYTE2          = 0x61
    EXT1_HIGH_BYTE2        = 0x62
    EXT1_LOW_BYTE2         = 0x63
    EXT2_HIGH_BYTE2        = 0x64
    EXT2_LOW_BYTE2         = 0x65
    EXT3_HIGH_BYTE2        = 0x66
    EXT3_LOW_BYTE2         = 0x67
    HOTTEST_DIODE_HB       = 0x6A
    HOTTEST_DIODE_LB       = 0x6B
    HOTTEST_STATUS         = 0x6C
    HOTTEST_CONFIG         = 0x6D
    PRODUCT_ID             = 0xFD
    MANUFACTURER_ID        = 0xFE
    REVISION               = 0xFF

@i2c.Interface.db.register("emc1813")
class Emc1813(i2c.Slave):
    def __init__(self, port, saddr=0x4D):
        super().__init__(port, "emc1813", saddr)

    def __getattr__(self, name, default=None):
        try:
            return super().__getattr__(name, default)
        except AttributeError:
            pass
        for ops, handler in [
            (Bytes, {"_get": self._byte_get, "_set": self._byte_set}),
        ]:
            for op in ops:
                for suffix, h in handler.items():
                    if op.name.lower() + suffix == name:
                        return functools.partial(h, op)
        raise AttributeError(name)

    def _byte_get(self, addr):
        r = self.port.cmd_read(self.saddr, 1)
        self.port.execute([i2c.Write(self.saddr, bytes([int(addr)])), r])
        return r.data[0]

    def _byte_set(self, addr, value):
        self.port.execute([i2c.Write(self.saddr, bytes([int(addr), value & 0xFF]))])

    def _temp_raw(self, hb_addr, lb_addr):
        hb = self._byte_get(hb_addr)
        lb = self._byte_get(lb_addr)
        return (hb << 3) | (lb >> 5)

    def _temp_to_celsius(self, raw, extended=None):
        if extended is None:
            extended = bool(self._byte_get(Bytes.CONFIG) & 0x04)
        if extended:
            return raw * 0.125 - 64.0
        return raw * 0.125

    def internal_temp_get(self):
        raw = self._temp_raw(Bytes.INT_HIGH_BYTE, Bytes.INT_LOW_BYTE)
        return self._temp_to_celsius(raw)

    def ext1_temp_get(self):
        raw = self._temp_raw(Bytes.EXT1_HIGH_BYTE, Bytes.EXT1_LOW_BYTE)
        return self._temp_to_celsius(raw)

    def ext2_temp_get(self):
        raw = self._temp_raw(Bytes.EXT2_HIGH_BYTE, Bytes.EXT2_LOW_BYTE)
        return self._temp_to_celsius(raw)

    def ext3_temp_get(self):
        raw = self._temp_raw(Bytes.EXT3_HIGH_BYTE, Bytes.EXT3_LOW_BYTE)
        return self._temp_to_celsius(raw)

    def all_temps_get(self):
        return {
            "internal": self.internal_temp_get(),
            "ext1":     self.ext1_temp_get(),
            "ext2":     self.ext2_temp_get(),
        }

    def all_regs_get(self):
        values = {}
        for op in Bytes:
            try:
                values[op] = self._byte_get(op)
            except Exception:
                values[op] = "NACK"
        return values
