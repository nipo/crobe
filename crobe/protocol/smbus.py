from . import base
from . import i2c
from ..db import Db, NoMatch

__all__ = ["Interface"]

class PecError(base.ProtocolError):
    pass

class ArpError(base.ProtocolError):
    pass

def pec(data, pec = 0):
    for b in data:
        for i in range(8):
            pec = (pec << 1) ^ (0x07 if (pec ^ (b << i)) & 0x80 else 0)
        pec &= 0xff
    return pec

@i2c.Interface.db.register("smbus")
class Interface(base.Interface):
    """
    SMBus protocol interface.
    """

    db = Db("I2C chip type")

    def __init__(self, port, name = None):
        base.Interface.__init__(self, port, (name or port.name) + "/SMBus")

    def start(self):
        self.port.freq_cap("smbus", 400e3)
        
    def pec_write(self, addr, data):
        p = pec(bytes([addr << 1]) + data)
        self.port.write(addr, data + bytes([p]))

    def pec_read(self, addr, size):
        r = self.port.read(addr, size + 1)
        data = r[:-1]
        pc = pec(bytes([(addr << 1) | 1]) + r)
        if pc != 0:
            raise PecError("")
        return data

    def pec_write_read(self, addr, data, size):
        read = self.port.cmd_read(addr, size + 1)
        self.port.execute([self.port.cmd_write(addr, data), read])

        rdata = read.data[:-1]
        pc = pec(bytes([addr << 1]) + data)
        pc = pec(bytes([(addr << 1) | 1]) + read.data, pc)
        if pc != 0:
            raise PecError("")
        return rdata

    def send_byte(self, addr, data):
        return self.pec_write(addr, bytes([data]))

    def receive_byte(self, addr):
        return self.pec_read(addr, 1)[0]

    def write_byte(self, addr, command, data):
        return self.pec_write(addr, bytes([command, data]))

    def read_byte(self, addr, command):
        return self.pec_write_read(addr, bytes([command]), 1)[0]

    def write_word(self, addr, command, data):
        return self.pec_write(addr, bytes([command]) + data.to_bytes(2, "little"))

    def read_word(self, addr, command):
        r = self.pec_write_read(addr, bytes([command]), 2)
        return int.from_bytes(r, "little")

    def process_call(self, addr, command, data):
        r = self.pec_write_read(addr, bytes([command]) + data.to_bytes(2, "little"), 2)
        return int.from_bytes(r, "little")

    def block_write(self, addr, command, data):
        self.pec_write(addr, bytes([command, len(data)]) + data)

    def block_read(self, addr, command):
        read_cmd = self.port.cmd_read(addr, 0x22)
        self.port.execute([self.port.cmd_write(addr, bytes([command])), read_cmd])

        l = read_cmd[0]
        rdata = read_cmd[1 : l + 1]

        pc = pec(bytes([addr << 1, command]))
        pc = pec(bytes([(addr << 1) | 1, l]) + read_cmd[:l+1], pc)
        if pc != 0:
            raise PecError("")
        return rdata

    def block_write_read(self, addr, command, data):
        read_cmd = self.port.cmd_read(addr, 0x22)
        self.port.execute([self.port.cmd_write(addr, bytes([command, len(data)]) + data), read_cmd])

        l = read_cmd[0]
        rdata = read_cmd[1 : l + 1]

        pc = pec(bytes([addr << 1, command, len(data)]) + data)
        pc = pec(bytes([(addr << 1) | 1, l]) + read_cmd[:l+1], pc)
        if pc != 0:
            raise PecError("")
        return rdata

    ARP_ADDR = 0x61
    
    def arp_prepare(self):
        try:
            return self.send_byte(self.ARP_ADDR, 1)
        except i2c.AddressNack:
            raise ArpError("No ARP-capable device on bus")

    def reset_device(self, addr = None):
        try:
            return self.send_byte(self.ARP_ADDR, 2 if addr is None else (addr << 1))
        except i2c.AddressNack:
            raise ArpError("No ARP-capable device on bus")

    def arp_get_udid(self, addr = None):
        try:
            r = self.block_read(self.ARP_ADDR, 3 if addr is None else ((addr << 1) | 1))
            if len(r) != 17:
                raise ArpError("Bad ARP get packet length")

            return r[:16], r[16]
        except i2c.AddressNack:
            raise ArpError("No ARP-capable device on bus")
            
    def arp_assign_address(self, udid, address):
        try:
            return self.block_write(4, udid + bytes([address]))
        except i2c.AddressNack:
            raise ArpError("No ARP-capable device on bus")

    def arp(self):
        address_pool = set(range(0x10, 0x5f))
        self.arp_prepare()
        # TODO: handle nack

        devices = {}
        
        while True:
            udid, addr = self.arp_get_udid()
            # TODO: handle nack
            # TODO: handle bad packet
            if addr == 0xff:
                addr = address_pool.pop()
                self.arp_assign_address(udid, addr)
                # TODO: handle nack

            # TODO: handle fixed address devices
            devices[addr] = udid

        return devices


    def child_spawn(self, sub):
        try:
            return self.db.call(sub, self)
        except NoMatch:
            pass
