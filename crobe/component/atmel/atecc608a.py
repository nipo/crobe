from ...protocol import i2c, base
from ...model import PortComponent
from ... import bitfield
import struct
import time
import enum

from . import atsec

@i2c.Interface.db.register("atecc")
class AtEcc(atsec.AtSec):
    class Command(enum.IntEnum):
        AES = 0x51
        CheckMac = 0x28
        Counter = 0x24
        DeriveKey = 0x1c
        ECDH = 0x43
        GenDig = 0x15
        GenKey = 0x40
        Info = 0x30
        KDF = 0x56
        Lock = 0x17
        MAC = 0x08
        Nonce = 0x16
        PrivWrite = 0x46
        Random = 0x1b
        Read = 0x02
        SecureBoot = 0x80
        SelfTest = 0x77
        Sign = 0x41
        SHA = 0x47
        UpdateExtra = 0x20
        Verify = 0x45
        Write = 0x12

    def __init__(self, bus, saddr = None):
        super().__init__(bus, name = "atecc", saddr = saddr)

    def config_address_change(self, new_address, allow_extra = True):
        config_before = self.read_config(0x10, 4)
        config_after = bytes([
            new_address << 1,
            config_before[1],
            config_before[2],
            (config_before[3] & 0xfe) | int(bool(allow_extra)),
            ])
        self.write_config(0x10, config_after)
        self.sleep()
        time.sleep(.1)
        self.wake()
        self.saddr = new_address

    class SlotConfig(bitfield.Bitfield):
        all = bitfield.Field(0, 16)
        ReadKey = bitfield.Field(0, 4)
        NoMac = bitfield.BooleanField(4)
        LimitedUse = bitfield.BooleanField(5)
        EncryptRead = bitfield.BooleanField(6)
        IsSecret = bitfield.BooleanField(7)
        WriteKey = bitfield.Field(8, 4)
        WriteConfig = bitfield.Field(12, 4)

    class SecureBootConfig(bitfield.Bitfield):
        all = bitfield.Field(0, 16)
        Mode = bitfield.MappingField(0, 2, ["Disabled", "FullBoth", "FullSig", "FullDig"])
        Persistent = bitfield.BooleanField(3)
        RandNonce = bitfield.BooleanField(4)
        SigDig = bitfield.Field(8, 4)
        PubKey = bitfield.Field(12, 4)

    class ChipOptions(bitfield.Bitfield):
        all = bitfield.Field(0, 16)
        POST = bitfield.BooleanField(0)
        IOProt = bitfield.BooleanField(1)
        KdfAes = bitfield.BooleanField(2)
        EcdhProt = bitfield.MappingField(8, 2, ["clear", "enc", "temp", "none"])
        KdfProt = bitfield.MappingField(10, 2, ["clear", "enc", "temp", "none"])
        IOKey = bitfield.Field(12, 4)

    class KeyConfig(bitfield.Bitfield):
        all = bitfield.Field(0, 16)
        Private = bitfield.BooleanField(0)
        PubInfo = bitfield.BooleanField(1)
        KeyType = bitfield.MappingField(2, 3, ["FRU0", "FRU1", "FRU2", "FRU3",
                                               "P256", "RFU5", "AES", "SHA"])
        Lockable = bitfield.BooleanField(5)
        ReqRandom = bitfield.BooleanField(6)
        ReqAuth = bitfield.BooleanField(7)
        AuthKey = bitfield.Field(8, 4)
        PersistentDisable = bitfield.BooleanField(12)
        X509Id = bitfield.Field(14, 2)
        
    def config_dump(self, printer = print):
        config = self.read_all_config()
        for i in range(0, len(config), 16):
            self.logger.info("Config %02x: %s", i, config[i:i+16].hex())

        sn = config[0:4] + config[8:13]
        printer("SN:", sn.hex())
        printer("Revision:", hex(int.from_bytes(config[4:8], "little")))
        printer("AES:", "enabled" if config[13] & 1 else "disabled")
        printer("Interface:", "i2c" if config[14] & 1 else "single-wire")
        printer("I2C address, base:", hex(config[16] >> 1), "user:", hex(config[85] >> 1))
        printer("Count match:", "enabled" if config[18] & 1 else "disabled", "slot:", config[18] >> 4)
        printer("I2C address storage:", "user or base" if config[19] & 1 else "base")
        printer("IO Level:", "Vcc referenced" if config[19] & 2 else "Fixed")
        printer("tWatchdog:", "10s" if config[19] & 4 else "1.3s")
        printer("Clock div:", hex(config[19] >> 3))
        for i in range(16):
            printer("Slot #%d:" % i, self.SlotConfig(all = int.from_bytes(config[20+2*i:22+2*i], "little")))
        printer("Counter 0:", config[52:60].hex())
        printer("Counter 1:", config[60:68].hex())
        printer("Lock:", "enabled" if config[68] & 0xf == 0xa else "disabled", "slot:", config[68] >> 4)
        printer("Volatile Key:", "enabled" if config[69] & 0x80 else "disabled", "slot:", config[69] & 0xf)
        printer("Secure boot:", self.SecureBootConfig(all = int.from_bytes(config[70:72], "little")))
        # TODO
        printer("KDF:", config[72:75].hex())
        printer("OTP/Data lock:", "unlocked" if config[86] == 0x55 else "locked")
        printer("Config lock:", "unlocked" if config[87] == 0x55 else "locked")
        slot_locking = ~int.from_bytes(config[88:90], "little")
        printer("Slot locked:", set(i for i in range(16) if (1 << i) & slot_locking))
        printer("Chip opts:", self.ChipOptions(all = int.from_bytes(config[90:92], "little")))
        printer("X509:", config[92:96].hex())
        for i in range(16):
            d = int.from_bytes(config[96+2*i:98+2*i], "little")
            printer("Key #%d config:" % i, self.KeyConfig(all = d))
        
    def start(self):
        super().start()
        assert self.product.startswith("ATECC")
        self.name = "%s@%02x" % (self.product, self.saddr)

        config = self.read_all_config()
        self.config = config
        for i in range(0, len(config), 16):
            self.logger.info("Config %02x: %s", i, config[i:i+16].hex())

    def info_key_valid(self, no):
        return self.command_info(1, no)[0] == 1

    class StateInfo(bitfield.Bitfield):
        TempKeyKeyId = bitfield.Field(0, 4)
        TempKeySourceFlag = bitfield.BooleanField(4)
        TempKeyGenDigData = bitfield.BooleanField(5)
        TempKeyGenKeyData = bitfield.BooleanField(6)
        TempKeyNoMacFlag = bitfield.BooleanField(7)
        AuthValid = bitfield.BooleanField(10)
        AuthKey = bitfield.Field(11, 4)
        TempKeyValid = bitfield.BooleanField(15)
    
    def info_state(self):
        ret = self.command_info(2)
        return self.StateInfo(all = int.from_bytes(ret[:2], "little"))

    def command_read(self, zone, address, length):
        assert length in [4, 32]
        param1 = int(zone) | (int(length == 32) << 7)
        # TODO: Set response time
        return self.command_run(self.Command.Read, param1, address)

    def command_write(self, zone, address, data, mac = b''):
        assert len(data) in [4, 32]
        param1 = int(zone) | (int(len(data) == 32) << 7) | (int(bool(mac)) << 6)
        # TODO: Set response time
        return self.command_run(self.Command.Write, param1, address, data + mac)

    def read_all_config(self):
        data = []
        for i in range(4):
            data.append(self.read_config(i * 32, 32))
        return b''.join(data)

    def read_config(self, offset, length):
        assert length in [4, 32]
        assert offset % length == 0

        return self.command_read(self.Zone.Config,
                                 self.ConfigAddress(offset = (offset % 32) // 4,
                                                    block = offset // 32).all,
                                 length)

    def write_config(self, offset, data):
        assert len(data) in [4, 32]
        assert offset % len(data) == 0

        self.command_write(self.Zone.Config,
                           self.ConfigAddress(offset = (offset % 32) // 4,
                                              block = offset // 32).all,
                           data)

    def command_update_extra(self, address, value):
        assert address in [84, 85]
        self.command_run(self.Command.UpdateExtra,
                         int(address == 85),
                         value)

    def command_counter_read(self, id, increment = False):
        r = self.command_run(self.Command.Counter,
                             int(bool(increment)),
                             int(id != 0))
        return int.from_bytes(r, "little")
