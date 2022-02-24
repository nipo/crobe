from ...adapter.jlink import JLinkInterface
import struct
import binascii
import time
import threading

__all__ = ["EfmStk"]

class EnergyMonitorThread(threading.Thread):
    def __init__(self, stk, callback):
        threading.Thread.__init__(self, name = "EFM32 Energy Monitor")
        self.stk = stk
        self.callback = callback
        self.done = False

    def run(self):
        while not self.done:
            ret = self.stk.energy_monitor_data_get()
            if ret is None:
                continue
            self.callback(*ret)

    def stop(self):
        self.done = True
            
    def join(self):
        threading.Thread.join(self)

class EfmStk(object):
    def __init__(self, jlink_intf):
        self.interface = jlink_intf

    def command(self, op0, args = {}):
        args_blob = b""
        for k, v in sorted(args.items()):
            args_blob += struct.pack("<BH", k, len(v)) + v

        cmd = struct.pack("<BLHH", 1, 0, op0, len(args_blob))
        chk = sum(cmd)

        blob = cmd + bytes([chk]) + args_blob
        s = self.interface.emucom_write(self.COM_CHANNEL_COMMANDS, blob)
        if s != len(blob):
            raise IOError("Short command write")

        response = self.interface.emucom_read(self.COM_CHANNEL_COMMANDS, 10)
        if len(response) < 10:
            raise IOError("Short response read")
        if response[0] != 1:
            raise IOError("Bad response opcode", response)
        chk = sum(response[:9])
        if chk != response[9]:
            raise ValueError("Reponse checksum failed", chk, sum(response[:9]))
        z, r0, size = struct.unpack("<LHH", response[1:9])

        response2 = self.interface.emucom_read(self.COM_CHANNEL_COMMANDS, size)
        if len(response2) < size:
            raise IOError("Short response2 read")

        r2, = struct.unpack("<H", response2[:2])
        if r2 != op0:
            raise ValueError("Unexpected response opcode")

        response2 = response2[2:]

        args = {}
        while response2:
            typ, length = struct.unpack("<BH", response2[:3])
            data = response2[3:3+length]
            args[typ] = data
            response2 = response2[3+length:]

        return r0, args

    def info_read(self):
        r0, info = self.command(self.COMMAND_INFO)
        return info

    @property
    def debug_mode(self):
        info = self.info_read()
        mode = info[self.INFO_DEBUG_MODE][0]
        return self.DEBUG_MODE[mode]

    @debug_mode.setter
    def debug_mode(self, mode):
        mode = self.DEBUG_MODE.index(mode.lower())
        self.command(self.COMMAND_SET_DEBUG_MODE, {0: struct.pack("<H", mode)})

    DEBUG_MODE = ["in","out","mcu","off"]
    INFO_DEBUG_MODE = 8

    COMMAND_INFO = 0x107
    COMMAND_SET_DEBUG_MODE = 0x303

    COM_CHANNEL_COMMANDS = 0x10000
    COM_CHANNEL_ENERGY_MONITOR = 0x10001
    COM_CHANNEL_ENERGY_MONITOR_FAST = 0x10002

    def energy_monitor(self, callable):
        t = EnergyMonitorThread(self, callable)
        t.start()
        return t
    
    def energy_monitor_data_get(self):
        blob = self.interface.emucom_read(self.COM_CHANNEL_ENERGY_MONITOR_FAST, 2048)

        if not any(blob[96:]):
            self.logger.trace("Calibrating...")
            return

        voltage, = struct.unpack("<f", blob[64:68])
        count = (len(blob) - 96) // 4
        currents = struct.unpack("<" + "f" * count, blob[96:])
        return voltage, [(ma * 1e-3 if ma > 0. else 0.) for ma in currents]
