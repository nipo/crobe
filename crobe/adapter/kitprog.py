from . import model
from ..protocol import i2c
from .. import bitstring
from ..util.pretty import metric
from collections import deque
import usb.core
import usb.util
import binascii
import time
import os
import math
import struct

__all__ = []

class Adapter(model.Adapter):
    supported_interfaces = ["i2c"]

    EP_SWD_IN = 0x01
    EP_SWD_OUT = 0x02
    EP_HOST_IN = 0x03
    EP_HOST_OUT = 0x04

    HOST_CONTROL_DIRECTION          = 0x01
    HOST_CONTROL_DIRECTION_WRITE    = 0x00
    HOST_CONTROL_DIRECTION_READ     = 0x01
    HOST_CONTROL_START              = 0x02
    HOST_CONTROL_RESTART            = 0x04
    HOST_CONTROL_STOP               = 0x08
    HOST_CONTROL_RESTART_HW         = 0x10
    HOST_CONTROL_CONFIGURE          = 0x20
    HOST_CONTROL_CONFIGURE_I2C_SPEED_1000			=	0x0C
    HOST_CONTROL_CONFIGURE_I2C_SPEED_400			=	0x04
    HOST_CONTROL_CONFIGURE_I2C_SPEED_100			=	0x00	
    HOST_CONTROL_CONFIGURE_I2C_SPEED_050			=	0x08	
    HOST_CONTROL_INTERFACE          = 0x0C

    HOST_I2C_NACK					=	0x00
    HOST_I2C_OK_ACK					=	0x01
    HOST_I2C_RESTART_FAIL			=	0x00
    HOST_I2C_RESTART_SUCCESS		=	0x01
    HOST_I2C_TIMEOUT				=	0x32

    HOST_MGMT_GET_POWER_SETTING		=	0x80
    HOST_MGMT_GET_KITPROG_VERSION	=	0x81
    HOST_MGMT_RESET_KITPROG			=	0x82
    HOST_MGMT_CONFIGURE_INTERFACE	=	0x8F
    HOST_MGMT_CONFIGURE_INTERFACE_I2C	=	0x00
    HOST_MGMT_CONFIGURE_INTERFACE_SWD	=	0x01
    HOST_MGMT_CONFIGURE_INTERFACE_NONE	=	0xff
    HOST_MGMT_ENTER_BOOTLOADER		=	0xA0

    def ctrl_out(self, op, value, index, data = b''):
        self.logger.debug("CTRL OUT %02x v %04x i %04x %s",
                          op, value, index,
                          binascii.b2a_hex(data))

        self.device.ctrl_transfer(0x40, bRequest = op,
                                  wValue = value, wIndex = index,
                                  data_or_wLength = data)

    def ctrl_in(self, op, value, index, length = 0):
        self.logger.debug("CTRL IN %02x v %04x i %04x s %d",
                          op, value, index, length)

        data = self.device.ctrl_transfer(0xc0, bRequest = op,
                                         wValue = value,
                                         wIndex = index,
                                         data_or_wLength = length)
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def bulk_out(self, ep, data, timeout = None):
        self.logger.debug("BULK OUT %02x %s", ep, binascii.b2a_hex(data))
        self.device.write(ep, data, int((timeout or 1.) * 1000))

    def bulk_in(self, ep, size, timeout = None):
        self.logger.debug("BULK IN %02x %d", ep, size)
        data = self.device.read(0x80 | ep, size, int((timeout or 1.) * 1000))
        return data

    def _version_get(self, what):
        data = self.ctrl_in(op = 0xb0,
                            value = self.OP_VERSION_READ,
                            index = what,
                            length = 2)
        return int.from_bytes(data, "little")

    @property
    def cpld_version(self):
        return self._version_get(1)

    @property
    def fw_version(self):
        return self._version_get(0)

    @classmethod
    def from_device(cls, d, pre):
        return cls(d, "%s-%d" % (pre, d.address))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)

        self.device = device

    @property
    def firmware_info(self):
        return "Firmware"

    def host_comm(self, control, length = 0, args = b'', rsize = 64):
        command = bytes([control, length]) + args
        self.bulk_out(self.EP_HOST_OUT, command)
        data = self.bulk_in(self.EP_HOST_IN, 64)[:rsize]
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def i2c_speed_set(self, speed):
        if speed < 100e3:
            actual = 50e3
            cmd = self.HOST_CONTROL_CONFIGURE | self.HOST_CONTROL_CONFIGURE_I2C_SPEED_050
        elif speed < 400e3:
            actual = 100e3
            cmd = self.HOST_CONTROL_CONFIGURE | self.HOST_CONTROL_CONFIGURE_I2C_SPEED_100
        elif speed < 1000e3:
            actual = 400e3
            cmd = self.HOST_CONTROL_CONFIGURE | self.HOST_CONTROL_CONFIGURE_I2C_SPEED_400
        else:
            actual = 1000e3
            cmd = self.HOST_CONTROL_CONFIGURE | self.HOST_CONTROL_CONFIGURE_I2C_SPEED_1000

        self.host_comm(cmd, rsize = 1)

        return actual

    def i2c_restart_hw(self):
        return bool(self.host_comm(self.HOST_CONTROL_RESTART_HW, rsize = 1)[0])

    def mgmt(self, command, args = b"", rsize = 0):
        blob = self.host_comm(self.HOST_CONTROL_START, args = bytes([command]) + args, rsize = rsize + 1)
        ack = bool(blob[0] & 0x01)
        power = bool(blob[0] & 0x04)
        data = blob[1:]
        return ack, power, data

    def mgmt_get_power_settings(self):
        ack, power, data = self.mgmt(self.HOST_MGMT_GET_POWER_SETTING)
        power_supply, i2c_speed, vtgt, vaux = struct.unpack("<BBHH", data[:6])
        return power, i2c_speed, vtgt, vaux

    def mgmt_get_version(self):
        ack, power, data = self.mgmt(self.HOST_MGMT_GET_KITPROG_VERSION, rsize = 3)
        hw_version, minor, major = data[:3]
        return hw_version, minor, major

    def mgmt_reset(self):
        ack, power, data = self.mgmt(self.HOST_MGMT_RESET_KITPROG)

    def mgmt_interface_set(self, intf):
        ack, power, data = self.mgmt(self.HOST_MGMT_CONFIGURE_INTERFACE, bytes([intf]))

    def mgmt_enter_bootloader(self):
        ack, power, data = self.mgmt(self.HOST_MGMT_ENTER_BOOTLOADER)

    def i2c_transfer(self, restart, stop, slave_addr, data_or_size):
        cmd = 0
        if restart:
            cmd |= self.HOST_CONTROL_RESTART
        elif restart is False:
            cmd |= self.HOST_CONTROL_START
        if stop:
            cmd |= self.HOST_CONTROL_STOP
        if isinstance(data_or_size, int):
            cmd |= self.HOST_CONTROL_DIRECTION_READ
            data = bytes([slave_addr])
            size = data_or_size
        else:
            cmd |= self.HOST_CONTROL_DIRECTION_WRITE
            data = bytes([slave_addr]) + data_or_size
            size = len(data_or_size)
        self.logger.info("i2c cmd %02x size %d data %s rsize %d",
                         cmd, size, binascii.b2a_hex(data), size + 1)
        rdata = self.host_comm(cmd, size, data, rsize = size + 1)
        saddr_ack = bool(rdata[0])
        if isinstance(data_or_size, int):
            return saddr_ack, rdata[1:]
        else:
            return saddr_ack, [bool(x) for x in rdata[1:]]

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            raise NotImplementedError("Unsupported interface %s" % interface_name)

        if self.device.is_kernel_driver_active(0):
            self.device.detach_kernel_driver(0)

        if interface_name.lower() == "i2c":
            return I2cInterface(self)

        raise NotImplementedError("Unsupported interface %s" % interface_name)

class I2cInterface(i2c.Interface):
    def __init__(self, port):
        i2c.Interface.__init__(self, port)

        version = self.port.mgmt_get_version()

        self.logger.info("Version: %s", version)

        self.port.mgmt_interface_set(self.port.HOST_MGMT_CONFIGURE_INTERFACE_I2C)
        self.port.i2c_speed_set(50e3)

    @property
    def freq(self):
        return self.__freq

    @freq.setter
    def freq(self, freq):
        self.__freq = self.port.i2c_speed_set(freq)

    def _execute(self, operation_list):
        ops = list(operation_list)

        prev = None

        for i, cur in enumerate(ops):
            next = ops[i+1] if i < len(ops) - 1 else None

            as_prev = bool(prev) and isinstance(prev, i2c.Read) == isinstance(cur, i2c.Read)

            self.logger.info("op: %s", cur)

            if isinstance(cur, i2c.Read):
                cur.data = b''
                for off in range(0, cur.size or 1, 60):
                    size = min(cur.size - off, 60)
                    last_chunk = off + size == cur.size
                    saddr_ack, data = self.port.i2c_transfer(None if as_prev else bool(prev),
                                                             not next and last_chunk,
                                                             cur.addr,
                                                             size)
                    if not saddr_ack:
                        self.port.i2c_transfer(None, True, 0, 0)
                        raise i2c.AddressNack()

                    cur.data += data
                    as_prev = True
            elif isinstance(cur, i2c.Write):
                for off in range(0, len(cur.data) or 1, 60):
                    size = min(len(cur.data) - off, 60)
                    last_chunk = off + size == len(cur.data)
                    chunk = cur.data[off : off + size]

                    saddr_ack, acks = self.port.i2c_transfer(None if as_prev else bool(prev),
                                                             not next and last_chunk,
                                                             cur.addr,
                                                             chunk)
                    if not saddr_ack:
                        self.port.i2c_transfer(None, True, 0, 0)
                        raise i2c.AddressNack()
                    if not all(acks[:-1]):
                        self.port.i2c_transfer(None, True, 0, 0)
                        raise i2c.DataNack()
            else:
                raise base.ProtocolError("Unknown I2C operation %s" % type(op))

@model.Enumerator.register
class Enumerator(model.Enumerator):
    adapter_class = Adapter
    prefix = "KitProg"

    def __init__(self):
        model.Enumerator.__init__(self, self.prefix)

    def start(self):
        for dev in usb.core.find(idVendor = 0x04b4, idProduct = 0xf139, find_all = True):
            self.child_add(self.adapter_class.from_device(dev, self.prefix))
        model.Enumerator.start(self)
