from . import base
from .. import bitstring
from enum import IntEnum
from ..db import Db, NoMatch
from ..model import PortComponent

__all__ = ["Interface"]

class ProtocolError(base.ProtocolError):
    pass

def crc8(data, init = 0):
    crc = init
    for d in data:
        for i in range(0, 8):
            b = ((d >> i) & 1) ^ (crc & 1)
            crc >>= 1
            if b:
                crc ^= 0x8c
    return crc

class Rom:
    def __init__(self, family, uid):
        self.family = family
        self.uid = uid

    @classmethod
    def from_raw(cls, blob):
        r = cls(blob[0], int.from_bytes(blob[1:7], 'little'))
        if blob[7] != r.crc:
            raise ValueError(f"Bad CRC, expected {r.crc:#04x}, got {blob[7]:#04x}")
        return r

    def __bytes__(self):
        return bytes([self.family]) + self.uid.to_bytes(6, "little") + bytes([self.crc])

    @property
    def crc(self):
        tmp = bytes([self.family]) + self.uid.to_bytes(6, "little")
        return crc8(tmp)

    def __str__(self):
        return f'<Family {self.family:#04x} UID {self.uid:#014x}>'

    def __eq__(self, other):
        return self.family == other.family and self.uid == other.uid
    
class Interface(base.Interface):
    """
    1-Wire protocol interface.
    """

    db = Db("1-Wire chip")

    tRSTL = 480e-6
    tRSTH = 480e-6
    tPDL = 15e-6
    tPDH = 60e-6
    tLOW0 = 60e-6
    tLOW1 = 15e-6
    tLOWR = 1e-6
    tSLOT = 60e-6
    tREC = 1e-6
    tRDV = 15e-6
    
    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "-1w")

    def start(self):
        self.freq_cap("base_slot", 16/87e-6)

        base.Interface.start(self)

        found = self.discovery()
        for f in found:
            self.child_add(self.db.call(f.family, self, f))
        super().start()

    def _execute(self, operation_list):
        raise NotImplementedError()

    def cmd_read(self, count):
        """
        Returns a read operation of count bits
        """
        return Read(count)

    def cmd_write(self, data):
        """
        Returns a write operation of bitstring
        """
        return Write(data)

    def cmd_reset(self):
        """
        Returns a reset operation
        """
        return Reset()

    def child_spawn(self, sub):
        return self.db.call(sub, self)
        
    def targetted_command(self, target, command, arg = b'', rsize = 0):
        cmds = []
        cmds.append(self.cmd_reset())
        wdata = bitstring.BitString(self.MATCH_ROM, 8) \
            + bitstring.BitString(bytes(target)) \
            + bitstring.BitString(command, 8)
        if arg:
            wdata += bitstring.BitString(arg)
        cmds.append(self.cmd_write(wdata))
        read = None
        if rsize:
            read = self.cmd_read(rsize * 8)
            cmds.append(read)
        self.execute(cmds)
        if read:
            return bytes(read.data)

    def global_command(self, command, arg = b'', rsize = 0):
        cmds = []
        cmds.append(self.cmd_reset())
        wdata = bitstring.BitString(command, 8)
        if arg:
            wdata += bitstring.BitString(arg)
        cmds.append(self.cmd_write(wdata))
        read = None
        if rsize:
            read = self.cmd_read(rsize * 8)
            cmds.append(read)
        self.execute(cmds)
        if read:
            return bytes(read.data)
        
    def discovery(self):
        found = []

        r = self.cmd_reset()
        self.execute([r])
        self.logger.info('Presence: %s', r.presence)
        if not r.presence:
            return []

        to_do = set()
        collision = True
        while collision or to_do:
            if not to_do:
                to_do.add(bitstring.BitString(0, 64))
            self.logger.debug("Collision search, to_do: %s", to_do)
            collision = False
            enumerated_address, collision_bit = self._do_search_rom(to_do.pop())
            self.logger.debug("Found %s, had collision at %s", enumerated_address, collision_bit)
            if not enumerated_address:
                continue
            try:
                rom = Rom.from_raw(bytes(enumerated_address))
            except ValueError as e:
                rom = None
                self.logger.warning("%s enumerated address %s", str(e), bytes(enumerated_address).hex())
            if rom:
                found.append(rom)
            if collision_bit is not None:
                to_do.add(bitstring.BitString(int(enumerated_address) ^ (1 << collision_bit), 64))
                collision = True

        return found

    def _do_search_rom(self, target):
        rdata = bitstring.BitString()
        collision = None
        self.execute([self.cmd_reset(), self.cmd_write(bitstring.BitString(self.SEARCH_ROM, 8))])
        for i in range(64):
            r = self.cmd_read(2)
            self.execute([r])
            if int(r.data) == 1:
                selected = bitstring.BitString(1, 1)
            elif int(r.data) == 2:
                selected = bitstring.BitString(0, 1)
            elif int(r.data) == 0:
                collision = collision or i
                selected = target[i:i+1]
            else:
                return None, i
            rdata += selected
            self.execute([self.cmd_write(selected)])
        return rdata, collision

    READ_ROM = 0x33
    SKIP_ROM = 0xcc
    MATCH_ROM = 0x55
    SEARCH_ROM = 0xf0
    OVERDRIVE_SKIP_ROM = 0x3c
    OVERDRIVE_MARCH_ROM = 0x69

@Interface.db.register_default
class Device(PortComponent):
    def __init__(self, port, rom, name = None):
        if name is None:
            name = "%012x" % rom.uid
        super().__init__(port, name)
        self.rom = rom

    def command(self, command, arg = b'', rsize = 0):
        return self.port.targetted_command(self.rom, command, arg, rsize)

    def cmd_wait(self, delay):
        return Wait(delay)

    def cmd_command(self, command, arg = b'', rsize = 0):
        return Command(command, arg, rsize)

    def execute(self, operation_list):
        cmds = []
        cmds.append(self.port.cmd_reset())
        cmds.append(self.port.cmd_write(
            bitstring.BitString(self.port.MATCH_ROM, 8) \
            + bitstring.BitString(bytes(self.rom))))

        rsp = []
        for op in operation_list:
            if isinstance(op, BusOperation):
                cmds.append(op)
                rsp.append(None)
            elif isinstance(op, Command):
                wdata = bitstring.BitString(op.command, 8)
                if op.arg:
                    wdata += bitstring.BitString(op.arg)
                cmds.append(self.port.cmd_write(wdata))
                if op.rsize:
                    r = self.port.cmd_read(op.rsize * 8)
                    rsp.append(r)
                    cmds.append(r)
                else:
                    rsp.append(None)
            else:
                raise ValueError(f"Unhandled operation {op}")

        self.port.execute(cmds)

        for cmd, rsp in zip(operation_list, rsp):
            if isinstance(cmd, Command) and cmd.rsize:
                op.data = bytes(rsp.data)
    
class BusOperation(base.Operation):
    pass

class Wait(BusOperation):
    def __init__(self, delay):
        self.delay = delay

    def __str__(self):
        return f'<Wait {self.delay:f}>'

class Read(BusOperation):
    def __init__(self, count):
        self.count = count

    # When executed
    data = None

    def __str__(self):
        return "<Read %d bits>" % (self.count)
        
class Write(BusOperation):
    def __init__(self, data):
        self.data = data
        
    def __str__(self):
        return "<Write %s>" % (self.data)

class Reset(BusOperation):
    def __init__(self):
        pass

    # when done
    presence = None
    
    def __str__(self):
        return "<Reset/Detect>"

class DeviceOperation(base.Operation):
    pass

class Command(DeviceOperation):
    def __init__(self, command, arg = b'', rsize = 0):
        self.command = command
        self.arg = bytes(arg)
        self.rsize = rsize

    # when executed
    data = None
        
    def __str__(self):
        return f"<Command {self.command:#04x}, {self.arg.hex()}, read {self.rsize}>"
