from . import base
import click
import binascii
import time

@base.cli.group(help = "STM32-Specific")
def stm32():
    pass

@stm32.command(help = "Secure target")
@click.option('-r', '--root', "roots", type = base.ROOT, multiple = True)
@base.field()
@click.option('--target', '-t', metavar = 'CRIT', help = 'Target criterion', default = "0")
def lock(roots, field, target):
    from crobe.target.model import Target

    roots[0].reset = True
    target = field.child_summon(target)
    bus = target.bus
    
    # Unlock Flash registers
    bus.u32_write(0x40022004, 0x45670123)
    bus.u32_write(0x40022004, 0xCDEF89AB)
    # Unlock Option Bytes
    bus.u32_write(0x40022008, 0x45670123)
    bus.u32_write(0x40022008, 0xCDEF89AB)
    # Set Write and Erase bit to prepare Option Byte erase
    bus.u32_write(0x40022010, 0x00000220)
    # Trigger operation (Option Byte erase)
    bus.u32_write(0x40022010, 0x00000260)
    # It is not possible to check the Status register in a commander file, therefore we 
    # just wait here a fixed amount of time
    time.sleep(.15)
    # Reset Write bit
    bus.u32_write(0x40022010, 0x00000020)
    # Reset Erase bit
    bus.u32_write(0x40022010, 0x00000000)
    # Set Flash lock. This step and the two previous steps cannot be combined.
    bus.u32_write(0x40022010, 0x00000080)
    # We do not actually write the ROP/nROP bytes, because erased (0xFF) state already sets ROP to Level 1
    # It is not possible to check the Status register in a commander file, therefore we 
    # just wait here a fixed amount of time
    time.sleep(.1)

@stm32.command(help = "Erase target")
@click.option('-r', '--root', "roots", type = base.ROOT, multiple = True)
@base.field()
@click.option('--target', '-t', metavar = 'CRIT', help = 'Target criterion', default = "0")
def erase(roots, field, target):
    from crobe.target.model import Target
    target = field.child_summon(target)

    f = target.info.flash_class(target.bus)
    f.mass_erase()
    f.opt_unlock()
    f.opt.write(bytes([0xa5, 0x5a]))

@stm32.command()
@click.argument("root", type = base.ROOT)
@click.argument("dumper", type = base.PROGRAM)
def attack(root, dumper):
    """
    Run RAM firmware that enables FPB and reset in flash mode, enabling
    possible extraction of firmware.

    Supposed to run firmware from https://github.com/JohannesObermaier/f103-analysis/ (H3 folder).

    This only works with dbg_fpga adapter as it requires two more pins to control boot modes.
    """
    from crobe.loadable.elf import ElfProgram
    from crobe.component.arm.coresight.scs import Scs
    from crobe.component.model import Register

    df = root
    df._open()
    
    print("Setting boot to RAM")
    df.regs.reg_update(df.regs.REG_IO, 0x3f003f << 4, 0x30003 << 4)
    time.sleep(.05)

    df.regs.mode_set("SWD")
    df.regs.reg_update(df.regs.REG_IO, 0x3f003f << 4, 0x30003 << 4)

    swd = df.swd
    swd.options.power = "supply", 3.3
    swd.baudrate = 115200
    swd.options.cycle_time = .3
    swd.option_set("reset")
    swd.turnaround_supported = False
    swd.start()
    
    swdp, = swd.children
    swdp.start()
    memap, = swdp.children
    memap.start()

    scs = Scs(memap, 0xe000e000)
    scs.enable(True)
    scs.cpu_halt()
    print(scs.cpu_state)
    (reg, value), = scs.cpu_regs_get([Register(15, "pc", 32, Register.Type.GPR, "GPR")]).items()
    print(hex(value))
    
    print("Shell code upload")
    for s in dumper:
        memap.mem_write(s.address, s.data)

    print("Dropping power")
    df.regs.execute([df.regs.cmd_reg_write(0, 0x00001)])
    while df.regs.target_voltage_get() > 1.9:
        pass
    df.regs.execute([df.regs.cmd_reg_write(0, 0x35001)])
    print("Power restored")

    print("Strobing reset")
    swd.reset(True)
    time.sleep(.002)
    swd.reset(False)

    print("Running from RAM")
    time.sleep(.1)

    print("Setting boot to Flash")
    df.regs.reg_update(df.regs.REG_IO, 0x3f003f << 4, 0x30000 << 4)
    time.sleep(.005)

    print("Strobing reset")
    swd.reset(True)
    swd.reset(False)

    print("Running from patched flash")

@stm32.command()
@click.option('-r', '--root', "roots", type = base.ROOT, multiple = True)
@base.field()
@click.option('--target', '-t', metavar = 'CRIT', help = 'Target criterion', default = "0")
def clone_identify(roots, field, target):
    """
    Try to identify clone
    """
    from crobe.component.arm.coresight.rom_table import RomTable
    from crobe.component.arm.coresight.scs import Scs
    from crobe.component.arm.mem_ap import MemAp
    from crobe.component.arm.coresight.etm import Etm
    from crobe.util.endian import swib_u32
    from crobe.target.model import Target
    from zlib import crc32

    target = field.child_summon(target)

    rom_tables = roots[0].children_of_class(RomTable)
    root_rom_table = rom_tables[0]
    print(f"Root ROMTABLE")
    print(f"At: {root_rom_table.base:#010x}")
    print(f"Use JEP106: {root_rom_table.use_jep106}")
    print(f"Part ID: {int(root_rom_table.partid):#010x} {root_rom_table.partid}")

    scs, = roots[0].children_of_class(Scs)
    print(f"SCS")
    print(f"CPU Name: {scs.cpu_name}")
    print(f"Part ID: {int(scs.partid):#010x} {scs.partid}")

    has_cs32_etm = root_rom_table.reg_read(5) & 1
    
    etms = roots[0].children_of_class(Etm)
    print(f"ETM")
    if etms:
        print(f"ETM present")
    else:
        print(f"ETM absent")

    print(f"ETM field in ROMTABLE: {has_cs32_etm}")
    
    maker = "Unknown"

    bus, = roots[0].children_of_class(MemAp)

    
    bootloader = bus.mem_read(0x1ffff000, 0x400)
#    bootloader = b"".join(bootloader[i:i+4][::-1] for i in range(0, len(bootloader), 4))
    bootloader_crc32 = crc32(bootloader)
    
    if root_rom_table.use_jep106:
        if root_rom_table.partid.jep106_bank == 0 and root_rom_table.partid.jep106_id == 0x20:
            maker = "STM32"
        if root_rom_table.partid.jep106_bank == 7 and root_rom_table.partid.jep106_id == 0x51:
            maker = "GD32"
        if root_rom_table.partid.jep106_bank == 4 and root_rom_table.partid.jep106_id == 0x3b:
            if has_cs32_etm:
                maker = "CS32"
            else:
                maker = "APM32"

            rom_7d0 = bus.mem_read(0x1ffff7d0, 4)
            if rom_7d0 == b"\xff\x00\xf3\x0c":
                maker = "APM32"
            if rom_7d0 == b"\xff\xff\xff\xff":
                rom_000 = bus.mem_read(0x1ffff000, 4)
                if rom_000 == b"\xfc\x01\x00\x20":
                    maker = "CS32"
                elif rom_000 == b"\x10\x09\x00\x20":
                    maker = "CH32"

    else:
        if root_rom_table.partid.jep106_bank == 5 and root_rom_table.partid.jep106_id == 0x55:
            maker = "HK32"
        if root_rom_table.partid.jep106_bank == 0 and root_rom_table.partid.jep106_id == 0:
            maker = "AIR32"
    
    print(f"Bootloader CRC32: {bootloader_crc32:#010x}")
    by_crc = {
        # From https://github.com/a-v-s/ucdev-demos/blob/master/todo/cortex_romtable/stm32f1/main.c
        0xda6104d0: "STM32F103x6",
        0x27377129: "STM32F103xB",
        0x1527d032: "GD32F101C6 or GC32F103CB",
        0x52d42adb: "HK32",
        0xdcbd2235: "CH32",

        # Own findings
        0x9af55669: "STM32F051R8T6", # Genuine chip from discovery board
        0xef201f8d: "STM32F103C8T6", # Genuine chip from discovery board
        0x0a72ef1c: "Unsure (FC)", # Unidentified chip, on frequency counter #2
        }

    bootloader_maker = by_crc.get(bootloader_crc32, "Unknown")

    print()
    print(f"Plausible source:")
    print(f"by ROMTABLE  : {maker}")
    print(f"by bootloader: {bootloader_maker}")
