from ...adapter.protocol import chipcon
from ...model import PortComponent
import binascii

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
    ChipconInfo("CC2543", 0x43, 1024, 0),
    ChipconInfo("CC2544", 0x44, 1024, 0),
    ChipconInfo("CC2545", 0x45, 1024, 0),
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

    def flash_write(self, page_address, data):
        assert len(data) == self.info.page_size, (len(data), self.info.page_size)
        assert (page_address % self.info.page_size) == 0
        self.port.halt()
        self.logger.info("Uploading data")
        c = FlashWrite(page_address, data, self.info)
        self.port.execute([c])
        self.logger.info("Waiting for CPU")
        self.port.wait_halted()

    def cmd_flash_read(self, address, size):
        return self.port.cmd_code_read(address, size)

    def xdata_read(self, addr):
        c = self.port.cmd_xdata_read(addr, 1)
        self.port.execute([c])
        return c.data[0]

class FlashWrite(chipcon.ComposedOperation):
    def __init__(self, address, data, info):
        self.address = address
        self.data = data
        self.info = info

    def decompose(self, port):
        routine = self.loader_code(self.address)
        ret = [port.cmd_sfr_write(0xc7, 0x04)]
        ret += port.cmd_xdata_write(0x1000, routine).decompose(port)
        ret += port.cmd_xdata_write(0x1000 + self.info.page_size, self.data).decompose(port)
        ret += [port.cmd_debug_instr(bytes([0x75, 0xc7, 0x51]), False),
                port.cmd_set_pc(0x9000 + self.info.page_size),
                port.cmd_resume(),
                ]
        return ret

    def done(self, ops):
        pass

    def __str__(self):
        return "<FlashWrite 0x%x %s>" % (self.address, binascii.b2a_hex(self.data))

    def loader_code(self, address):
        page = ((address >> 8) // self.info.word_size) & 0x7E
        wcount = self.info.page_size // self.info.word_size

        return bytes([
            0x75, 0xAD, page,       #     MOV FADDRH, #imm;
            0x75, 0xAC, 0x00,       #     MOV FADDRL, #00;
            0x75, 0xAE, 0x01,       #     MOV FLC, #01H; // ERASE
                                    #     ; Wait for flash erase to complete
                                    # eraseWaitLoop:
            0xE5, 0xAE,             #     MOV A, FLC;
            0x20, 0xE7, 0xFB,       #     JB ACC_BUSY, eraseWaitLoop;
                                    #     ; Initialize the data pointer
            0x90, 0xF0, 0x00,       #     MOV DPTR, #0F000H;
                                    #     ; Outer loops
            0x7F, wcount >> 8,      #     MOV R7, #imm;
            0x7E, wcount & 0xff,    #     MOV R6, #imm;
            0x75, 0xAE, 0x02,       #     MOV FLC, #02H; // WRITE
                                    #         ; Inner loops
                                    # writeLoop:
            0x7D, self.info.word_size, #  MOV R5, #imm;
                                    # writeWordLoop:
            0xE0,                   #             MOVX A, @DPTR;
            0xA3,                   #             INC DPTR;
            0xF5, 0xAF,             #             MOV FWDATA, A;
            0xDD, 0xFA,             #         DJNZ R5, writeWordLoop;
                                    #         ; Wait for completion
                                    # writeWaitLoop:
            0xE5, 0xAE,             #         MOV A, FLC;
            0x20, 0xE6, 0xFB,       #         JB ACC_SWBSY, writeWaitLoop;
            0xDE, 0xF1,             #     DJNZ R6, writeLoop;
            0xDF, 0xEF,             #     DJNZ R7, writeLoop;
                                    #     ; Done, fake a breakpoint
            0xA5                    #     DB 0xA5;
        ])                                           

class MassErase(chipcon.ComposedOperation):
    def __init__(self):
        pass

    def decompose(self, port):
        return [
            port.cmd_debug_instr(bytes([0x00]), False),
            port.command(bytes([chipcon.Command.CHIP_ERASE])),
            port.cmd_delay(20e-3),
            ]

    def done(self, ops):
        pass

    def __str__(self):
        return "<MassErase>"

@chipcon.Interface.db.register(*[chip.id for chip in chips])
def chip_hook(chipid, intf):
    chip = [c for c in chips if c.id == chipid][0]
    return CC_8051(intf, chip)
