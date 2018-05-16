from ...protocol import chipcon
from ...model import PortComponent
import binascii
import struct

class ChipconInfo:
    def __init__(self, name, id, page_size, word_size):
        self.name = name
        self.id = id
        self.page_size = page_size
        self.word_size = word_size

chips = [
    ChipconInfo("CC1110", 0x01, 0, 0),
    ChipconInfo("CC2430", 0x85, 0, 0),
    ChipconInfo("CC2431", 0x89, 0, 0),
    ChipconInfo("CC2510", 0x81, 0, 0),
    ChipconInfo("CC2511", 0x91, 0, 0),
    ChipconInfo("CC2530", 0xa5, 2048, 4),
    ChipconInfo("CC2531", 0xb5, 2048, 4),
    ChipconInfo("CC2533", 0x95, 1024, 4),
    ChipconInfo("CC2543", 0x43, 1024, 4),
    ChipconInfo("CC2544", 0x44, 1024, 4),
    ChipconInfo("CC2545", 0x45, 1024, 4),
    ChipconInfo("CC2540", 0x8d, 2048, 4),
    ]

class CC_8051(PortComponent):
    SFR_P0 = 0x80
    SFR_P1 = 0x90
    SFR_P2 = 0xa0
    SFR_PERCFG = 0xf1
    SFR_ACFG = 0xf2
    SFR_P0SEL = 0xf3
    SFR_P1SEL = 0xf4
    SFR_P2SEL = 0xf5
    SFR_P0DIR = 0xfd
    SFR_P1DIR = 0xfe
    SFR_P2DIR = 0xff
    SFR_P0INP = 0x8f
    SFR_P1INP = 0xf6
    SFR_P2INP = 0xf7
    SFR_P0IFG = 0x89
    SFR_P1IFG = 0x8a
    SFR_P2IFG = 0x8b
    SFR_PICTL = 0x8c
    SFR_P0IEN = 0xab
    SFR_P1IEN = 0x8d
    SFR_P2IEN = 0xac
    SFR_PMUX = 0xae
    REG_OBSSEL = staticmethod(lambda x: 0x6243 + x)
    REG_CHIPINFO = staticmethod(lambda x: 0x6276 + x)

    def __init__(self, port, info):
        PortComponent.__init__(self, port, "Ti " + info.name)
        self.info = info

        self.ping(0xde)
        self.ping(0xad)
        self.ping(0xbe)
        self.ping(0xef)

        chipinfo = self.xdata_read(self.REG_CHIPINFO(0))
        if chipinfo & 7 == 4:
            self.flash_size = (16 * 1024) << ((chipinfo >> 4) & 7)

        chipinfo = self.xdata_read(self.REG_CHIPINFO(1))
        self.ram_size = (chipinfo + 1) * 1024

    def ping(self, value):
        ping = chipcon.Ping(value)
        self.port.execute([ping])
        assert ping.data[0] == value

    def start(self):
        PortComponent.start(self)

    def cmd_clk_init(self):
        return ClkInit()

    def cmd_mass_erase(self):
        return MassErase()

    def flash_page_erase(self, page_address):
        assert (page_address % self.info.page_size) == 0
        self.port.execute([
            self.port.cmd_clk_init(),
            self.port.cmd_halt(),
            self.port.cmd_xdata_write(self.FADDR_ADDR, struct.pack("<H", page_address // self.info.word_size)),
            self.port.cmd_xdata_write(self.FCTL_ADDR, b"\x01"),
            ])
        while self.xdata_read(self.FCTL_ADDR) & 0x80:
            pass

    def flash_write(self, page_address, data):
        assert len(data) == self.info.page_size, (len(data), self.info.page_size)
        assert (page_address % self.info.page_size) == 0
        self.port.execute([
            self.port.cmd_clk_init(),
            self.port.cmd_halt(),
            ])

        self.port.execute([
            self.port.cmd_write_config(0x22),
            self.port.cmd_xdata_write(self.DMA_DESC_ADDR,
                                      self._dma_desc(self.DBGDATA_ADDR,
                                                     self.BUFFER_ADDR,
                                                     self.info.page_size,
                                                     self.TRIGGER_DBG_BW,
                                                     self.INC_DST)),
            self.port.cmd_data_write(self.DMA_DESC0_PTR_SFR, struct.pack("<L", self.DMA_DESC_ADDR)),
            self.port.cmd_data_write(self.DMA_ARM_SFR, bytes([1 << 0])),
            self.port.cmd_burst_write(data),
            ])

        self.port.execute([
            self.port.cmd_xdata_write(self.DMA_DESC_ADDR + 8,
                                      self._dma_desc(self.BUFFER_ADDR,
                                                     self.FWDATA_ADDR,
                                                     self.info.page_size,
                                                     self.TRIGGER_FLASH,
                                                     self.INC_SRC)),
            self.port.cmd_data_write(self.DMA_DESC1_PTR_SFR, struct.pack("<L", self.DMA_DESC_ADDR + 8)),
            self.port.cmd_xdata_write(self.FADDR_ADDR, struct.pack("<H", page_address // self.info.word_size)),
            self.port.cmd_data_write(self.DMA_ARM_SFR, bytes([1 << 1])),
            self.port.cmd_xdata_write(self.FCTL_ADDR, b"\x06"),
            ])

        while self.xdata_read(self.FCTL_ADDR) & 0x80:
            pass

    BUFFER_ADDR = 0x0300
    DMA_DESC_ADDR = 0x0200

    DBGDATA_ADDR = 0x6260

    FCTL_ADDR = 0x6270
    FADDR_ADDR = 0x6271 # LE
    FWDATA_ADDR = 0x6273

    DMA_DESC0_PTR_SFR = 0xd4 # LE
    DMA_DESC1_PTR_SFR = 0xd2 # LE
    DMA_IRQ_SFR = 0xd1
    DMA_ARM_SFR = 0xd6

    TRIGGER_DBG_BW = 31
    TRIGGER_FLASH = 18
    INC_SRC = 0x42
    INC_DST = 0x11

    @staticmethod
    def _dma_desc(src, dst, size, trigger, inc):
        return struct.pack(">HHHBB", src, dst, size, trigger, inc)

    def cmd_flash_read(self, address, size):
        return self.port.cmd_code_read(address, size)

    def xdata_read(self, addr):
        c = self.port.cmd_xdata_read(addr, 1)
        self.port.execute([c])
        return c.data[0]

class MassErase(chipcon.ComposedOperation):
    def __init__(self):
        pass

    def decompose(self, port):
        return [
            port.cmd_halt(),
            port.cmd_debug_instr(bytes([0x00]), False),
            port.command(bytes([chipcon.Command.CHIP_ERASE])),
            port.cmd_delay(20e-3),
            port.cmd_debug_init(),
            port.cmd_get_chip_id(),
            port.cmd_debug_init(),
            port.cmd_write_config(0x22),
            ]+port.cmd_clk_init().decompose(port)+[
            port.cmd_halt(),
            ]

    def done(self, ops):
        pass

    def __str__(self):
        return "<MassErase>"

@chipcon.Interface.db.register(*[chip.id for chip in chips])
def chip_hook(chipid, intf):
    chip = [c for c in chips if c.id == chipid][0]
    return CC_8051(intf, chip)
