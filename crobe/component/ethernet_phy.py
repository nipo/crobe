from ..protocol import smi
from .. import bitfield
import enum

class Register(enum.IntEnum):
    Control = 0
    Status = 1
    PhyId0 = 2
    PhyId1 = 3
    AutonegAdv = 4
    AutonegPartnerBase = 5
    AutonegExpansion = 6
    AutonegNextPageTransmit = 7
    AutonegNextPageReceive = 8
    MasterSlaveControl = 9
    MasterSlaveStatus = 10
    PseControl = 11
    PseStatus = 12
    MmdAccessControl = 13
    MmdAccessAddressData = 14
    ExtendedStatus = 15

class Control(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    reset = bitfield.BooleanField(15)
    loopback = bitfield.BooleanField(14)
    speed0 = bitfield.MappingField(13, 1, [10, 100])
    autoneg = bitfield.BooleanField(12)
    power_down = bitfield.BooleanField(11)
    isolate = bitfield.BooleanField(10)
    aneg_restart = bitfield.BooleanField(9)
    fd = bitfield.BooleanField(8)
    col_test = bitfield.BooleanField(7)

class Status(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    extended = bitfield.BooleanField(0)
    jabber_detect = bitfield.BooleanField(1)
    link = bitfield.BooleanField(2)
    autoneg_able = bitfield.BooleanField(3)
    remote_fault = bitfield.BooleanField(4)
    autoneg_done = bitfield.BooleanField(5)
    mf_pre_suppr = bitfield.BooleanField(6)
    ext_status = bitfield.BooleanField(8)
    tech_100bt2 = bitfield.BooleanField(9)
    tech_100bt2_fd = bitfield.BooleanField(10)
    tech_10bte = bitfield.BooleanField(11)
    tech_10bte_fd = bitfield.BooleanField(12)
    tech_100btx = bitfield.BooleanField(13)
    tech_100btx_fd = bitfield.BooleanField(14)
    tech_100bt4 = bitfield.BooleanField(15)

class AutonegAdv(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    remote_fault = bitfield.BooleanField(13)
    pause = bitfield.MappingField(10, 2, ["None", "Symmetric", "Asymmetric", "Both"])
    tech_100btxfd = bitfield.BooleanField(8)
    tech_100btx = bitfield.BooleanField(7)
    tech_10btfd = bitfield.BooleanField(6)
    tech_10bt = bitfield.BooleanField(5)
    selector = bitfield.Field(0, 5)

class AutonegLpAbility(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    np = bitfield.BooleanField(15)
    ack = bitfield.BooleanField(14)
    remote_fault = bitfield.BooleanField(13)
    pause = bitfield.BooleanField(10)
    tech_100bt4 = bitfield.BooleanField(9)
    tech_100btxfd = bitfield.BooleanField(8)
    tech_100btx = bitfield.BooleanField(7)
    tech_10btfd = bitfield.BooleanField(6)
    tech_10bt = bitfield.BooleanField(5)
    selector = bitfield.Field(0, 5)

class AutonegExpansion(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    par_detec_fault = bitfield.BooleanField(4)
    lp_np_able = bitfield.BooleanField(3)
    np_able = bitfield.BooleanField(2)
    page_rx = bitfield.BooleanField(1)
    lp_aneg_able = bitfield.BooleanField(0)

class BasePage(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    selector = bitfield.Field(0, 5)
    ability = bitfield.Field(5, 7)
    t = bitfield.BooleanField(11)
    xnp = bitfield.BooleanField(12)
    rf = bitfield.BooleanField(13)
    ack = bitfield.BooleanField(14)
    np = bitfield.BooleanField(15)

class MessagePage(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    message = bitfield.Field(0, 11)
    t = bitfield.BooleanField(11)
    # Can comply
    ack2 = bitfield.BooleanField(12)
    # Should be 1
    mp = bitfield.BooleanField(13)
    ack = bitfield.BooleanField(14)
    np = bitfield.BooleanField(15)

class UnformattedPage(bitfield.Bitfield):
    all = bitfield.Field(0, 16)
    u = bitfield.Field(0, 11)
    t = bitfield.BooleanField(11)
    # Can comply
    ack2 = bitfield.BooleanField(12)
    # Should be 0
    mp = bitfield.BooleanField(13)
    ack = bitfield.BooleanField(14)
    np = bitfield.BooleanField(15)
    
@smi.Interface.db.register("eth_phy")
@smi.Interface.db.register_default
class Clause22EthernetPhy(smi.C22Slave):
    REGISTERS = Register
    REGISTER_MAP = {
        Register.Control: Control,
        Register.Status: Status,
        Register.AutonegExpansion: AutonegExpansion,
        Register.AutonegAdv: AutonegAdv,
        Register.AutonegPartnerBase: AutonegLpAbility,
    }

    def __init__(self, bus, name = "phy", phyad = None):
        super().__init__(bus, name = name, phyad = phyad)

    def reg_set(self, no, value):
        if reg <= 0x1f:
            return self.write(no, value)
        else:
            return self.ext_write(0x1f, no, value)

    def reg_get(self, no):
        if reg <= 0x1f:
            return self.read(no)
        else:
            return self.ext_read(0x1f, no)

    def link_status_get(self):
        bmcr = self.cmd_read(0)
        bmsr = self.cmd_read(1)
        anar = self.cmd_read(4)
        lpar = self.cmd_read(5)
        gsr = self.cmd_read(0xf)
        gcr = self.cmd_read(0x9)
        gst1 = self.cmd_read(0xa)

        self.port.execute([bmcr, bmsr, gsr, gcr, anar, lpar, gst1])
        bmsr = Status(all = bmsr.data)

        local_support = set()
        local_adv = set()
        remote_adv = set()

        for bit, token in {15:"100bt4", 14:"100btx-fd", 13:"100btx-hd", 12:"10bte-fd",
                           11:"10bte-hd", 10:"100bt2-fd", 9:"100bt2-hd"}.items():
            if bmsr.all & (1 << bit):
                local_support.add(token)
        if bmsr.all & 0x0100:
            for bit, token in {15:"1000bx-fd", 14:"1000bx-hd", 13:"1000bt-fd", 12:"1000bt-hd"}.items():
                if gsr.data & (1 << bit):
                    local_support.add(token)

        if not bmsr.link:
            return "down"

        if bmsr.autoneg_able and (bmcr.data & 0x1000):
            for bit, token in {9:"100bt4", 8:"100btx-fd", 7:"100btx-hd", 6:"10bte-fd",
                               5:"10bte-hd"}.items():
                if anar.data & (1 << bit):
                    local_adv.add(token)
                if lpar.data & (1 << bit):
                    remote_adv.add(token)
            
            for bit, token in {11:"1000bt-fd", 10:"1000bt-hd"}.items():
                if gst1.data & (1 << bit):
                    remote_adv.add(token)

                if gcr.data & (1 << (bit-2)):
                    local_adv.add(token)
        else:
            m0 = bool(bmcr.data & 0x2000)
            m1 = bool(bmcr.data & 0x0040)
            d = bool(bmcr.data & 0x0100)
            if m1 and not m0:
                if d:
                    local_adv.add("1000bt-fd")
                else:
                    local_adv.add("1000bt-hd")
            elif not m1 and m0:
                if d:
                    local_adv.add("100btx-fd")
                else:
                    local_adv.add("100btx-hd")
            elif not m1 and not m0:
                if d:
                    local_adv.add("10bte-fd")
                else:
                    local_adv.add("10bte-hd")
        common = local_support & local_adv & remote_adv
        print(f"Local: {local_support}")
        print(f"Local ADV: {local_adv}")
        print(f"Remote ADV: {remote_adv}")
        print(f"Common: {common}")

        return common
            
