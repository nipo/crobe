from ...model import PortComponent
from ...protocol import i2c
from ...bitfield import *
from ...util.pretty import metric
import enum
import math

class Tcpc(i2c.AddressedSlave):
    _by_addr = {}
    _by_class = {}

    @classmethod
    def at(cls, address):
        def _dec(reg_class):
            cls._by_addr[address] = reg_class
            cls._by_class[reg_class] = address
            return reg_class
        return _dec

    def __init__(self, bus, saddr):
        super().__init__(bus, "tcpc", saddr)

    def reg_read(self, reg):
        try:
            addr = int(reg)
        except TypeError:
            addr = self._by_class[reg]
        reg_class = self._by_addr[addr]
        
        reg_size = (reg_class._width + 7) // 8

        raw = super().mem_read(addr, reg_size)
        value = int.from_bytes(raw, "little")
        pretty = reg_class(value)

        self.logger.trace("Reg read %s (%02x): %s (%s)", reg_class.__name__, reg, pretty, raw.hex())

        return pretty

    def reg_write(self, reg, value = None):
        if value is None:
            reg = reg.__class__
            value = int(reg)

        try:
            addr = int(reg)
        except TypeError:
            addr = self._by_class[reg]
        reg_class = self._by_addr[addr]
        
        pretty = reg_class(int(value))

        reg_size = reg_class._width // 8
        raw = int(value).to_bytes(reg_size, "little")

        self.logger.trace("Reg write %s (%02x): %s (%s)", reg_class.__name__, reg, pretty, raw.hex())
        super().mem_write(addr, raw)

@i2c.Interface.db.register("tcpc")
def tcpc_get(bus):
    return Tcpc(bus, None)

@Tcpc.at(0x00)
class VendorId(Bitfield):
    value = Field(0, 16)

@Tcpc.at(0x02)
class ProductId(Bitfield):
    value = Field(0, 16)

@Tcpc.at(0x04)
class DeviceId(Bitfield):
    value = Field(0, 16)

@Tcpc.at(0x06)
class TypeCRevision(Bitfield):
    res = Field(8, 8)
    major = Field(4, 4)
    minor = Field(0, 4)

@Tcpc.at(0x08)
class PDRevision(Bitfield):
    pd_revision_major = Field(12, 4)
    pd_revision_minor = Field(8, 4)
    pd_version_major = Field(4, 4)
    pd_version_major = Field(0, 4)

@Tcpc.at(0x0a)
class PDInterfaceRevision(Bitfield):
    pd_ibs_revision_major = Field(12, 4)
    pd_ibs_revision_minor = Field(8, 4)
    pd_ibs_version_major = Field(4, 4)
    pd_ibs_version_major = Field(0, 4)

@Tcpc.at(0x10)
class Alert(Bitfield):
    vendor_defined = BooleanField(15)
    extended = BooleanField(14)
    extended_status = BooleanField(13)
    sop = BooleanField(12)
    sink_disconnect = BooleanField(11)
    overflow = BooleanField(10)
    fault = BooleanField(9)
    vbus_low = BooleanField(8)
    vbus_high = BooleanField(7)
    sop_tx_success = BooleanField(6)
    sop_tx_discarded = BooleanField(5)
    sop_tx_failed = BooleanField(4)
    hard_reset_rx = BooleanField(3)
    sop_rx = BooleanField(2)
    power = BooleanField(1)
    cc = BooleanField(0)

@Tcpc.at(0x12)
class AlertMask(Alert):
    pass

@Tcpc.at(0x14)
class PowerStatusMask(Bitfield):
    debug_accessory_connected = BooleanField(7)
    tcpc_initialization_status = BooleanField(6)
    sourcing_nondefault_voltage = BooleanField(5)
    sourcing_vbus = BooleanField(4)
    vbus_detection = BooleanField(3)
    vbus_present = BooleanField(2)
    vconn_present = BooleanField(1)
    sinking_vbus = BooleanField(0)

@Tcpc.at(0x15)
class FaultStatusMask(Bitfield):
    all_ats_default = BooleanField(7)
    force_off_vbus = BooleanField(6)
    auto_discharge_failed = BooleanField(5)
    force_discharge_failed = BooleanField(4)
    ocp = BooleanField(3)
    ovp = BooleanField(2)
    vconn_over_current = BooleanField(1)
    i2c_interface_error = BooleanField(0)

@Tcpc.at(0x16)
class ExtendedStatusMask(Bitfield):
    all = Field(0, 8)
    vsafe0v_status = BooleanField(0)

@Tcpc.at(0x17)
class AlertExtendedMask(Bitfield):
    all = Field(0, 8)
    timer_expired = BooleanField(2)
    source_fast_role_swap = BooleanField(1)
    sink_fast_role_swap = BooleanField(0)
    
@Tcpc.at(0x18)
class ConfigStandardOutput(Bitfield):
    Hiz_outputs= BooleanField(7)
    debug_accessory_connected = BooleanField(6)
    audio_accessory_connected = BooleanField(5)
    active_cable_connected = BooleanField(4)
    mux_control = MappingField(2, 2, ["None", "USB3.1", "DPAlt4", "USB3.1+DP2"])
    connection_present = BooleanField(1)
    connector_orientation = MappingField(0, 1, ["Normal", "Flipped"])

@Tcpc.at(0x19)
class TcpcControl(Bitfield):
    smbus_pec = BooleanField(7)
    looking4connection = BooleanField(6)
    watchdog = BooleanField(5)
    debug_accessory = BooleanField(4)
    i2c_clock_stretching = MappingField(2, 2, ["Disabled", None, "Limited", "WithoutAlert"])
    bist_test = BooleanField(1)
    plug_orientation = BooleanField(0)

@Tcpc.at(0x1a)
class RoleControl(Bitfield):
    drp = BooleanField(6)
    rp_value = MappingField(4, 2, ["Default", "1.5A", "3.0A", None])
    cc2 = MappingField(2, 2, ["Ra", "Rp", "Rd", "Open"])
    cc1 = MappingField(0, 2, ["Ra", "Rp", "Rd", "Open"])

@Tcpc.at(0x1b)
class FaultControl(Bitfield):
    force_off_vbus = BooleanField(4, inverted = True)
    vbus_discharge_fault = BooleanField(3, inverted = True)
    ocp = BooleanField(2, inverted = True)
    ovp = BooleanField(1, inverted = True)
    vconn_ovc = BooleanField(0, inverted = True)
    
@Tcpc.at(0x1c)
class PowerControl(Bitfield):
    fast_role_swap = BooleanField(7)
    vbus_voltage_monitor = BooleanField(6, inverted = True)
    voltage_alarms = BooleanField(5, inverted = True)
    auto_discharge = BooleanField(4)
    bleed_discharge = BooleanField(3, inverted = True)
    force_discharge = BooleanField(2, inverted = True)
    vconn_power_supported = BooleanField(1)
    enable_vconn = BooleanField(0, inverted = True)
    
@Tcpc.at(0x1d)
class CcStatus(Bitfield):
    looking4connection = BooleanField(5)
    connect_result = BinaryField(4, "Rp", "Rd")
    cc2_state = MappingField(2, 2, ["Open", "Ra/Def", "Rd/1.5", "Res/3.1"])
    cc1_state = MappingField(0, 2, ["Open", "Ra/Def", "Rd/1.5", "Res/3.1"])
    
@Tcpc.at(0x1e)
class PowerStatus(PowerStatusMask):
    pass
    
@Tcpc.at(0x1f)
class FaultStatus(FaultStatusMask):
    pass
    
@Tcpc.at(0x20)
class ExtendedStatus(ExtendedStatusMask):
    pass
    
@Tcpc.at(0x21)
class AlertExtended(AlertExtendedMask):
    pass

class Opcode(enum.IntEnum):
    wake_i2c = 0x11
    disable_vbus_detect = 0x22
    enable_vbus_detect = 0x33
    disable_sink_vbus = 0x44
    sink_vbus = 0x55
    disable_source_vbus = 0x66
    source_vbus_default_voltage = 0x77
    source_vbus_nondefault_voltage = 0x88
    look4connection = 0x99
    rx_one_more = 0xaa
    send_frswap_signal = 0xcc
    reset_transmit_buffer = 0xdd
    reset_receive_buffer = 0xee
    i2c_idle = 0xff

@Tcpc.at(0x23)
class Command(Bitfield):
    all = Field(0, 8)
    command = EnumField(0, 8, Opcode)

@Tcpc.at(0x24)
class DeviceCapabilities(Bitfield):
    all = Field(0, 32)
    message_disable_disconnect = BooleanField(30)
    generic_timer = BooleanField(29)
    long_message = BooleanField(28)
    smbus_pec = BooleanField(27)
    source_frswap = BooleanField(26)
    sink_frswap = BooleanField(25)
    watchdog_timer = BooleanField(24)
    sink_disconnect = BooleanField(23)
    stop_discharge = BooleanField(22)
    vbus_alarm_lsb = MappingField(20, 2, [25, 50, 100, None])
    vconn_power = MappingField(1, 3, [1, 1.5, 2, 3, 45, 6, "Ext"])
    vconn_ovc = BooleanField(16)
    vbus_nondefault_target = BooleanField(15)
    vbus_ocp_reporting = BooleanField(14)
    vbus_ovp_reporting = BooleanField(13)
    bleed_discharge = BooleanField(12)
    force_discharge = BooleanField(11)
    vbus_measurement = BooleanField(10)
    source_resistor = MappingField(8, 2, ["Rp", "Rp+1.5", "Rp+3", None])
    power_roles = MappingField(5, 3, ["Dual w/o DRP", "Source", "Sink", "Sink w/ DAM", "DRP only", "All", "Source,Sink,DRP", None])
    all_sop = BooleanField(4)
    source_vconn = BooleanField(3)
    sink_vbus = BooleanField(2)
    source_nondefault_vbus = BooleanField(1)
    source_vbus = BooleanField(0)
    
@Tcpc.at(0x28)
class StandardInputCapabilities(Bitfield):
    frswap = Field(3, 2)
    vbus_external_over_voltage = BooleanField(2)
    vbus_external_over_current = BooleanField(1)
    force_off_vbus = BooleanField(0)

@Tcpc.at(0x29)
class StandardOutputCapabilities(Bitfield):
    vbus_sink_disconnect_detect = BooleanField(7)
    debug_accessory = BooleanField(6)
    vbus_present = BooleanField(5)
    audio_adapter_accessory = BooleanField(4)
    active_cable = BooleanField(3)
    mux_configuration = BooleanField(2)
    connection = BooleanField(1)
    connector_orientation = BooleanField(0)

@Tcpc.at(0x2a)
class ConfigExtended1(Bitfield):
    frswap_bidirectional_pin = BooleanField(1)
    standard_input_source_frswap = BooleanField(0)

@Tcpc.at(0x2c)
class GenericTimer(Bitfield):
    tenth_ms = Field(0, 16)

@Tcpc.at(0x2e)
class MessageHeaderInfo(Bitfield):
    all = Field(0, 16)
    source = BinaryField(4, "Peer", "Cable")
    data_role = BinaryField(3, "UFP", "DFP")
    pd_revision = MappingField(1, 2, ["1.0", "2.0", "3.0", None])
    power_role = BinaryField(0, "Sink", "Source")

@Tcpc.at(0x2f)
class ReceiveDetect(Bitfield):
    message_disable_disconnect = BooleanField(7)
    cable_reset = BooleanField(6)
    hard_reset = BooleanField(5)
    sop_dbg2 = BooleanField(4)
    sop_dbg1 = BooleanField(3)
    enable_sop2 = BooleanField(2)
    enable_sop1 = BooleanField(1)
    enable_sop = BooleanField(0)

@Tcpc.at(0x30)
class ReadableByteCount(Bitfield):
    value = Field(0, 8)

@Tcpc.at(0x70)
class VbusVoltage(Bitfield):
    scale = MappingField(10, 2, [1, 2, 4, None])
    value = Field(0, 10)

@Tcpc.at(0x72)
class VbusSinkDisconnectThreshold(Bitfield):
    trip_point = ScaledField(0, 10, 25)

@Tcpc.at(0x74)
class VbusSinkDischargeThreshold(VbusSinkDisconnectThreshold):
    pass

@Tcpc.at(0x76)
class VbusVoltageAlarmHiCfg(VbusSinkDisconnectThreshold):
    pass

@Tcpc.at(0x78)
class VbusVoltageAlarmLoCfg(VbusSinkDisconnectThreshold):
    pass

@Tcpc.at(0x7a)
class VbusNondefaultTarget(VbusSinkDisconnectThreshold):
    pass
