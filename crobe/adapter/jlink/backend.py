from .. import model
from ...model import Component
from ... import bitstring
import os
import binascii
import struct
import sys
import math
import logging
import usb.core
import usb.util
import enum
from collections import deque

__all__ = ["JlinkError", "Handle", "Device", "Context"]

class Config(enum.IntEnum):
    UsbAddress        = 0x00
    EnumerationMethod = 0x01 #00/FF:Usb,01: RealSn,02: FakeSn
    Power             = 0x04 # to , 0x08)
    FakeSn            = 0x08 # to , 0x0c)
    IpAddr            = 0x20 # to , 0x24)
    IpNet             = 0x24 # to , 0x28)
    Hwaddr            = 0x30 # to , 0x36)
    Nickname          = 0x50 # to , 0x70)
    
class Capabilities(enum.IntEnum):
    GetHwVersion = 1
    WriteDcc = 2
    AdaptiveClocking = 3
    ReadConfig = 4
    WriteConfig = 5
    Trace = 6
    WriteMem = 7
    ReadMem = 8
    GetSpeeds = 9
    ExecCode =10
    GetFreeMemory =11
    GetHwInfo =12
    SetTargetPower =13
    ResetStopTimed =14
    ShortenLife =15
    MeasureRtckReact =16
    SelectTif =17
    RwMemArm79 =18
    GetCounters =19
    ReadDcc =20
    GetCpuCaps =21
    ExecCpuCmd =22
    Swo =23
    WriteDccEx =24
    UpdateFirmwareEx =25
    FileIo =26
    Register =27
    Indicators =28
    TestNetSpeed =29
    Rawtrace =30
    GetExtCaps =31
    JtagWrite =32
    Emucom =33
    ExecCpu2Cmd =34
    GetCpu2Caps =35
    TestNet =36
    Powertrace =37
    Ethernet =38
    SetSwdioDir =39
    EnableDisableSwclk =40
    EnableDisableJtagIf =41
    SetClearTck =42
    GetCpu2CapsVersion =43
    PcodeExec =44
    ProtVersion =45
    SetEmuOption =46
    CdcExec =47
    CdcSetHookFuncs =48
    HandleBmi =49
    HandleGpio =50
    MergeCommands =51

class HwInfo(enum.IntEnum):
    TargetPower = 0
    PowerOvercurrent = 1
    Itarget = 2
    ItargetPeak = 3
    ItargetPeakOperation = 4
    ItargetMaxTime0 =10
    ItargetMaxTime1 =11
    ItargetMaxTime2 =12

class Counter(enum.IntEnum):
    Time = 0
    Connections = 1

class HwType(enum.IntEnum):
    Jlink = 0
    Flasher = 2
    JlinkPro = 3

class Tif(enum.IntEnum):
    Jtag = 0
    Swd = 1
# Dont care about the others for now. Dont enumerate them
#    Bdm3 = 2
#    Fine = 3
#    Icsp = 4
#    Spi = 5
#    C2 = 6

class JlinkError(Exception):
    def __init__(self, message, code):
        Exception.__init__(self, message)
        self.message = message
        self.code = code

class Handle(Component):
    def __init__(self, device):
        super().__init__("j/%s/%s" % (device.bus, device.address))
        cfg = device.get_active_configuration()
        if cfg.bConfigurationValue == 0:
            device.set_configuration(1)
            cfg = device.get_active_configuration()
        self.intf = None
        self.__speed_khz = 1000
        for intf in cfg:
            if intf.bInterfaceClass == 0xff \
               and intf.bInterfaceSubClass == 0xff \
               and intf.bInterfaceProtocol == 0xff:
                self.intf = intf
                break

        if self.intf is None:
            raise ValueError("Bad JLink device")

        self.cfg = cfg

        self.out_ep = usb.util.find_descriptor(self.intf,
                                               custom_match =
                                               lambda e:
                                               usb.util.endpoint_direction(e.bEndpointAddress) ==
                                               usb.util.ENDPOINT_OUT)
        self.in_ep = usb.util.find_descriptor(self.intf,
                                              custom_match =
                                              lambda e:
                                              usb.util.endpoint_direction(e.bEndpointAddress) ==
                                              usb.util.ENDPOINT_IN)
        caps = GetCaps()
        self.execute([caps])

        if (1 << Capabilities.GetExtCaps) & caps.data:
            caps = GetCapsEx()
            self.execute([caps])

        self.capabilities = set()
        for i in Capabilities:
            if (1 << i) & caps.data:
                self.capabilities.add(i)

        if Capabilities.GetHwVersion in self.capabilities:
            ver = GetHwVersion()
            self.execute([ver])
            self.hardware_version = ver.type, ver.major, ver.minor, ver.rev
        else:
            self.hardware_version = 0, 0, 0, 0

        sp = GetSpeeds()
        self.execute([sp])
        self.__speeds = sp.base_freq, sp.min_div
        self.__register_handle = None

        if Capabilities.Register in self.capabilities:
            try:
                self.__register()
            except Exception as e:
                import traceback
                traceback.print_exc()

    def __register(self):
        register = Register(True)
        self.execute([register])
        self.__register_handle = register.handle

        import weakref
        weakref.finalize(self, self.__close,
                         self.out_ep, self.in_ep,
                         self.__register_handle)

    @staticmethod
    def __close(out_ep, in_ep, handle):
        reg = Register(False, handle)
        out_ep.write(bytes([reg.cmd]) + reg.cmd_args)
        in_ep.read(2048)

    def close(self):
        if Capabilities.Register in self.capabilities and self.__register_handle is not None:
            register = Register(False, self.__register_handle)
            self.execute([register])
            
    def execute(self, commands):
        for c in commands:
            self.execute_command(c)

    def execute_command(self, op):
        cmd = bytes([op.cmd]) + op.cmd_args
        variable, rsp_size = op.rsp_size

        self.logger.protocol("< %s", cmd.hex())
        self.out_ep.write(cmd)
        if not rsp_size:
            return

        rsp = self.in_ep.read(2048)
        rsp = bytes(rsp)
        self.logger.protocol("> %s", rsp.hex())

        if variable:
            rs = op.response_size_parse(rsp)
            if rs:
                rsp = bytes(self.in_ep.read(rs))
                self.logger.protocol("> %s", rsp.hex())
            else:
                rsp = b''

        op.response_handle(rsp)

    @property
    def firmware_version(self):
        ver = GetVersion()
        self.execute([ver])
        return ver.data.split('\n')[0]

    @property
    def config(self):
        if Capabilities.ReadConfig not in self.capabilities:
            raise NotImplementedError("Incapable hardware")

        cfg = ReadConfig()
        self.execute([cfg])
        return cfg.data

    @config.setter
    def config(self, value):
        if Capabilities.WriteConfig not in self.capabilities:
            raise NotImplementedError("Incapable hardware")

        value = bytes(value)
        self.logger.trace("Writing configuration blob: %r", value.hex())

        self.execute([WriteConfig(value)])

        if self.config != value:
            print("Config write failed. You may have more chance using JLinkExe.")
            print("Try the following commands:")
            for i, (before, after) in enumerate(zip(self.config, value)):
                if before != after:
                    print("wconf %02x, %02x" % (i, after))
            
            raise RuntimeError("Config write failed")

    @property
    def nickname(self):
        return self.config[Config.Nickname].split(b'\x00')[0]

    @nickname.setter
    def nickname(self, nickname):
        self.logger.info("Setting probe nickname: %s", nickname)
        if nickname:
            tmp = nickname.encode("utf-8")[:31] + b'\x00'
        else:
            tmp = b''
        tmp = tmp.ljust(32, b'\xff')
        c = bytearray(self.config)
        c[Config.Nickname : Config.Nickname + 32] = tmp
        self.config = c
    
    def hardware_info_get(self, item):
        info = GetHwInfo(item)
        self.execute([info])
        return info.info[0]

    def counter_get(self, item):
        info = GetCounters(item)
        self.execute([info])
        return info.info[0]

    def jtag_io(self, tms, tdi):
        v = self.hardware_version[0]
        ret_bs = False

        if isinstance(tms, bitstring.BitString):
            tms_len = len(tms)
            tms = bytes(tms)
        elif isinstance(tms, bytes):
            tms_len = len(tms) * 8
        else:
            raise ValueError(tms)
        if isinstance(tdi, bitstring.BitString):
            tdi_len = len(tdi)
            tdi = bytes(tdi)
            ret_bs = True
        elif isinstance(tdi, bytes):
            tdi_len = len(tdi) * 8
            ret_bs = False
        else:
            raise ValueError(tdi)

        assert tms_len == tdi_len
        assert 0 < tms_len <= 0xffff

        if v >= 5:
            cmd = [HwJtag3(tms, tdi, tms_len)]
        else:
            cmd = [HwJtag(tms, tdi, tms_len), HwJtagGetResult()]
        self.execute(cmd)

        tdo = cmd[0].tdo
        if ret_bs:
            tdo = bitstring.BitString(tdo, tms_len)
        ret = cmd[-1].ret

        assert ret == 0
        return tdo

    def pin_state_get(self):
        cmd = GetState()
        self.execute([cmd])
        return dict(
            vcc = cmd.vcc,
            tck = cmd.tck,
            tdi = cmd.tdi,
            tdo = cmd.tdo,
            tms = cmd.tms,
            srst = cmd.srst,
            trst = cmd.trst,
            )

    @property
    def speed_khz(self):
        return self.__speed_khz

    @speed_khz.setter
    def speed_khz(self, khz):
        base_freq, min_div = self.__speeds

        if khz:
            div = max((int(base_freq / khz * 1000 + .5), min_div))
        else:
            div = min_div

        self.__speed_khz = int(base_freq / div / 1000. + .5)

        self.execute([SetSpeed(div)])

    @property
    def speed_range(self):
        base_freq, min_div = self.__speeds
        return base_freq / 0xfffe, base_freq / min_div

    @property
    def interface(self):
        cmd = GetCurrentIf()
        self.execute([cmd])
        return Tif(cmd.data)

    @interface.setter
    def interface(self, interface):
        self.execute([SelectIf(interface)])
        assert self.interface == interface, (self.interface, interface)
        self.speed_khz = self.__speed_khz
    
    @property
    def resetn(self):
        return self.pin_state_get()["srst"]

    @resetn.setter
    def resetn(self, value):
        if value:
            cmd = HwReset1()
        else:
            cmd = HwReset0()
        self.execute([cmd])

    @property
    def tresetn(self):
        return self.pin_state_get()["trst"]

    @tresetn.setter
    def tresetn(self, value):
        if value:
            cmd = HwTrst1()
        else:
            cmd = HwTrst0()
        self.execute([cmd])

    @property
    def power(self):
        return self.__target_power

    @power.setter
    def power(self, enabled):
        self.execute([SetKsPower(int(bool(enabled)))])
        self.__target_power = enabled

    def firmware_read(self, addr, size, k = None):
        key = k or 0x4f455701

        key_set = SetKey(key)
        self.execute([key_set])
        assert key_set.retval == 0

        dumpers = []
        for off in range(addr, addr + size, 0x100):
            dumpers.append(ReadFirmware(off, 0x100, key))
        self.execute(dumpers)

        return b''.join(x.data for x in dumpers)
        
class Command:
    cmd = 0
    cmd_args = b''
    rsp_size = False, 0
    data = None

    def response_size_parse(self, blob):
        return int.from_bytes(blob, "little")

    def response_handle(self, blob):
        self.data = blob

class CommandIntRsp(Command):
    def response_handle(self, blob):
        self.data = int.from_bytes(blob, "little")
        
class GetVersion(Command):
    cmd = 0x01
    rsp_size = True, 2

    def response_handle(self, blob):
        self.data = str(blob, 'utf-8', 'ignore')

class GetSpeeds(Command):
    cmd = 0xC0
    rsp_size = False, 6

    def response_handle(self, blob):
        self.base_freq = int.from_bytes(blob[:4], "little")
        self.min_div = int.from_bytes(blob[4:], "little")

class GetMaxMemBlock(CommandIntRsp):
    cmd = 0xD4
    rsp_size = False, 4

class GetCaps(CommandIntRsp):
    cmd = 0xE8
    rsp_size = False, 4

class GetCapsEx(CommandIntRsp):
    cmd = 0xED
    rsp_size = False, 32

class GetHwVersion(Command):
    cmd = 0xF0
    rsp_size = False, 4

    def response_handle(self, blob):
        self.type, self.major, self.minor, self.rev = blob

class GetState(Command):
    cmd = 0x07
    rsp_size = False, 8

    def response_handle(self, blob):
        a, b, self.tck, self.tdi, self.tdo, self.tms, self.srst, self.trst = blob
        self.vcc = (a | (b << 8)) / 1000.

class CommandMaskRsp(Command):
    def __init__(self, mask):
        self.mask = mask

    @property
    def cmd_args(self):
        return int(self.mask).to_bytes(4, "little")

    @property
    def rsp_size(self):
        bit_count = 0
        m = int(self.mask)
        while m:
            if m & 1:
                bit_count += 1
            m >>= 1

        return False, 4 * bit_count

    def response_handle(self, data):
        m = int(self.mask)
        n = 0
        info = {}
        while m:
            if m & 1:
                bit_count += 1
            m >>= 1
            n += 1
            info[n] = int.from_bytes(data[bit_count * 4 : (bit_count+1) * 4], "little")
        self.info = info

class GetHwInfo(CommandMaskRsp):
    cmd = 0xC1

class GetCounters(CommandMaskRsp):
    cmd = 0xC2

class MeasureRtckReact(Command):
    cmd = 0xF6
    rsp_size = False, 16

    def response_handle(self, blob):
        self.result, self.min, self.max, self.avg = struct.unpack('<LLLL', blob)

class ResetTrst(Command):
    cmd = 0x02
    rsp_size = False, 0

class SetSpeed(Command):
    cmd = 0x05
    rsp_size = False, 0

    def __init__(self, div):
        self.div = div

    @property
    def cmd_args(self):
        v = 0xffff if self.div is None else max(1, min(0xfffe, int(self.div)))
        return v.to_bytes(2, "little")

class If(CommandIntRsp):
    cmd = 0xC7
    rsp_size = False, 4

class GetAvailableIf(If):
    cmd_args = b'\xff'

class GetCurrentIf(If):
    cmd_args = b'\xfe'

class SelectIf(If):
    def __init__(self, interface):
        self.interface = interface

    @property
    def cmd_args(self):
        return bytes([self.interface])

class SetEmuOpts(Command):
    rsp_size = False, True
    cmd = 0x0e

    def __init__(self, addr, length, param2 = 0, param3 = 0, args = b''):
        self.addr = addr
        self.length = length
        self.param2 = param2
        self.param3 = param3
        self.args = args

    @property
    def cmd_args(self):
        return struct.pack("<LLLL", self.addr, self.length, self.param2, self.param3) \
            + self.args

    def response_handle(self, blob):
        rs = blob[0]
        self.response = blob[1:rs+1]

class SetKey(SetEmuOpts):
    rsp_size = False, True

    def __init__(self, key):
        super().__init__(addr = 0x182, length = key)

    def response_handle(self, blob):
        super().response_handle(blob)
        self.retval = int.from_bytes(self.response, "little")

class ReadFirmware(Command):
    cmd = 0xfe
    rsp_size = False, 256

    def __init__(self, addr, size, key):
        self.addr = addr
        self.size = size
        self.rsp_size = False, self.size + 1
        self.key = key

    @property
    def cmd_args(self):
        return struct.pack("<LL", self.addr, self.size)

    def response_handle(self, blob):
        k = self.key
        data = []
        for i in range(0, len(blob), 4):
            w = int.from_bytes(blob[i:i+4], "little")
            x = w ^ k
            data.append(x.to_bytes(4, 'little'))
            k = x ^ 0xa5a5a5a5
        self.data = b''.join(data)

class Register(Command):
    cmd = 0x09
    rsp_size = False, 76

    def __init__(self, enable, handle = 0):
        self.enable = enable
        self.handle = handle

    @property
    def cmd_args(self):
        # arg1, Register: 0x64, Unregister 0x65
        # arg2-5, PID
        # arg6-9, addr
        # arg10, IID
        # arg11, CID
        # arg12-13, handle
        import os
        return struct.pack("<BLLBBH", 0x64 if self.enable else 0x65, os.getpid(), 0,
                           0, 0, self.handle)

    def response_handle(self, blob):
        self.handle, count, entry_size, info_size = struct.unpack("<HHHH", blob[:8])
        self.entries = []
        for i in range(count):
            self.entries.append(blob[8 + entry_size * i : 8 + entry_size * i + entry_size])
        self.info = blob[-info_size:]
            

class SetKsPower(Command):
    cmd = 0x08
    rsp_size = False, 0

    def __init__(self, on):
        self.on = bool(on)

    @property
    def cmd_args(self):
        return bytes([int(self.on)])

class HwClock(Command):
    cmd = 0xC8
    rsp_size = False, 1

class HwTms0(Command):
    cmd = 0xC9

class HwTms1(Command):
    cmd = 0xCA

class HwData0(Command):
    cmd = 0xCB

class HwData1(Command):
    cmd = 0xCC

class HwJtag(Command):
    cmd = 0xCD

    def __init__(self, tms, tdi, length):
        self.tms = tms
        self.tdi = tdi
        self.length = length

    @property
    def rsp_size(self):
        return False, (self.length + 7) // 8

    @property
    def cmd_args(self):
        return self.length.to_bytes(2, "little") + self.tms + self.tdi

    def response_handle(self, data):
        self.tdo = data

class HwJtag2(Command):
    cmd = 0xCE

    def __init__(self, tms, tdi, length):
        self.tms = tms
        self.tdi = tdi
        self.length = length

    @property
    def rsp_size(self):
        return False, (self.length + 7) // 8

    @property
    def cmd_args(self):
        return b'\x00' + self.length.to_bytes(2, "little") + self.tms + self.tdi

    def response_handle(self, data):
        self.tdo = data[:-1]
        self.ret = data[-1]

class HwJtag3(Command):
    cmd = 0xCF

    def __init__(self, tms, tdi, length):
        self.tms = tms
        self.tdi = tdi
        self.length = length

    def response_size_parse(self, blob):
        self.tdo = blob
        return 1

    @property
    def rsp_size(self):
        return True, (self.length + 7) // 8

    @property
    def cmd_args(self):
        return b'\x00' + self.length.to_bytes(2, "little") + self.tms + self.tdi

    def response_handle(self, data):
        self.ret = data[0]

#class HwJtagWrite(Command):
#    cmd = 0xD5

class HwJtagGetResult(Command):
    cmd = 0xD6
    rsp_size = False, 1

    def response_handle(self, data):
        self.ret = data[0]

class HwTrst0(Command):
    cmd = 0xDE

class HwTrst1(Command):
    cmd = 0xDF

#class WriteDCC(Command):
#    cmd = 0xF1

class ResetTarget(Command):
    cmd = 0x03

#class HwReleaseResetStOpEx(Command):
#    cmd = 0xD0

#class HwReleaseResetStOpTimed(Command):
#    cmd =0xd1

class HwReset0(Command):
    cmd = 0xDC

class HwReset1(Command):
    cmd = 0xDD

class GetLicenses(CommandIntRsp):
    cmd = 0xE6
    rsp_size = False, 256

    def response_handle(self, data):
        self.serial = int.from_bytes(data[:4], "little")
        self.licenses = []
        for off in range(0x20, 0x100, 0x10):
            l = data[off : off + 0x10].strip(b'\xff')
            if not l:
                break
            self.licenses.append(str(l, "ascii"))

class GetCpuCaps(CommandIntRsp):
    cmd = 0xE9
    rsp_size = False, 4

    def __init__(self, family, interface):
        self.family = int(family)
        self.interface = int(interface)

    @property
    def cmd_args(self):
        return bytes([self.family, self.interface, 0, 0])

#class ExecCpuCmd(Command):
#    cmd = 0xEA

#class WriteMem(Command):
#    cmd = 0xF4

#class ReadMem(Command):
#    cmd = 0xF5

#class WriteMemArm79(Command):
#    cmd = 0xF7

#class ReadMemArm79(Command):
#    cmd = 0xF8

class ReadConfig(Command):
    cmd = 0xF2
    rsp_size = False, 256

    def response_handle(self, data):
        self.data = data

class WriteConfig(Command):
    cmd = 0xF3

    def __init__(self, config):
        assert len(config) == 256
        self.config = config

    @property
    def cmd_args(self):
        return bytes(self.config)

def main():
    from ... import root
    import sys

    r = root.root(sys.argv[1])
    r.execute([GetVersion()])
    

if __name__ == "__main__":
    main()

