from ....part_id import PartId
from .soc import SoC
import binascii

class ZynqPs(SoC):
    def __init__(self, name, dp):
        SoC.__init__(self, name, dp)

    def start(self):
        SoC.start(self)
        fuse = self.efuse_read()
        for i in range(0, len(fuse), 8):
            self.logger.info("Fuse %02x: %s", i, str(binascii.b2a_hex(fuse[i:i+8]), "ascii"))

    def efuse_read(self):
        b = self.buses[0]

        b.execute([
            b.cmd_u32_write(self.FUSE_WR_UNLOCK_REG, self.FUSE_WR_UNLOCK_MAGIC),
            b.cmd_u32_write(self.FUSE_CONTROL_REG, self.FUSE_CONTROL_WR_DISABLE),
            b.cmd_u32_write(self.FUSE_WR_LOCK_REG, self.FUSE_WR_LOCK_MAGIC),
            ])

        blob = b.mem_read(self.FUSE_APB_REG(0), 0x800)
        ret = []
        for off in range(0, len(blob), 8 * 4):
            ret.append(sum((x & 1) << i for (i, x) in enumerate(blob[off:off + 8 * 4:4])))
        ret = bytes(ret)

        b.execute([
            b.cmd_u32_write(self.FUSE_WR_UNLOCK_REG, self.FUSE_WR_UNLOCK_MAGIC),
            b.cmd_u32_write(self.FUSE_CONTROL_REG, self.FUSE_CONTROL_RD_DISABLE|self.FUSE_CONTROL_WR_DISABLE),
            b.cmd_u32_write(self.FUSE_WR_LOCK_REG, self.FUSE_WR_LOCK_MAGIC),
            ])

        return ret

    FUSE_WR_LOCK_REG          = 0xf800d000
    FUSE_WR_LOCK_MAGIC        = 0x767b
    FUSE_WR_UNLOCK_REG        = 0xf800d004
    FUSE_WR_UNLOCK_MAGIC      = 0xdf0d
    FUSE_LOCK_STATUS_REG      = 0xf800d008
    FUSE_LOCK_STATUS_LOCKED   = 0x00000001
    FUSE_CONFIG_REG           = 0xf800d00c
    FUSE_CONFIG_REDUNDANCY    = 0x00010000
    FUSE_CONFIG_TSU_H_A       = 0x00002000
    FUSE_CONFIG_TSU_H_CS      = 0x00001000
    FUSE_CONFIG_TSU_H_PS      = 0x00000f00
    FUSE_CONFIG_MARGIN_NORMAL = 0x00000000
    FUSE_CONFIG_MARGIN_1      = 0x00000010
    FUSE_CONFIG_MARGIN_2      = 0x00000020
    FUSE_CONFIG_CLK_DIV_8     = 0x00000003
    FUSE_STATUS_REG           = 0xf800d010
    FUSE_STATUS_BISR_DONE     = 0x80000000
    FUSE_STATUS_BISR_GO       = 0x40000000
    FUSE_STATUS_BISR_BLANK    = 0x00100000
    FUSE_STATUS_SDEBUG_DIS    = 0x00010000
    FUSE_STATUS_WR_PROTECTED  = 0x00003000
    FUSE_STATUS_TRIM_MASK     = 0x000000fc
    FUSE_CONTROL_REG          = 0xf800d014
    FUSE_CONTROL_PS_ENABLE    = 0x00000010
    FUSE_CONTROL_WR_DISABLE   = 0x00000002
    FUSE_CONTROL_RD_DISABLE   = 0x00000001
    FUSE_PGM_STBW_REG         = 0xf800d018
    FUSE_RD_STBW_REG          = 0xf800d01c

    FUSE_APB_REG = staticmethod(lambda x: 0xf800e020 + x * 4)
    APB_WRITE_PROT1        = 0x020 / 4
    APB_WRITE_PROT2        = 0x024 / 4
    APB_ROM_CRC_EN         = 0x028 / 4
    APB_RSA_AUTH_EN        = 0x02c / 4
    APB_DFT_JTAG_DISABLE   = 0x030 / 4
    APB_DFT_MODE_DISABLE   = 0x034 / 4
    APB_CUSTOMER_KEY_BEGIN = 0x080 / 4
    APB_CUSTOMER_KEY_END   = 0x580 / 4
    APB_REDUNDANCY_OFFSET  = 0x800 / 4
    APB_ROM_UART_ENABLE    = 0x5c0 / 4
    APB_ROM_NONSEC_INITB   = 0x5c4 / 4

# Actually Xilinx screwed their root RomTable PID register
# It actually decodes to Ikanos/0x3b[23]
@SoC.db.register(PartId.from_idcode(0x203b3313),
                 PartId.from_idcode(0x003b2313))
def zynq_ps_probe(dp):
    return ZynqPs("Zynq PS", dp)
