from . import model
from ..protocol import i2c, swd
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
import threading

__all__ = []

class BackgroundWriter(threading.Thread):
    def __init__(self, adapter, ep, data, timeout):
        threading.Thread.__init__(self)
        self.adapter = adapter
        self.ep = ep
        self.data = data
        self.timeout = timeout

    def run(self):
        self.adapter.bulk_out(self.ep, self.data, int(self.timeout * 1000))

class Adapter(model.Adapter):
    # KitProg implements Cypress USB-I2C bridge as documented in
    # AN2352 (http://www.cypress.com/file/42296/download).
    
    supported_interfaces = ["i2c", "swd"]

    EP_SWD_IN    = 0x01
    EP_SWD_OUT   = 0x02
    EP_I2USB_IN  = 0x03
    EP_I2USB_OUT = 0x04

    I2USB_TXN_DIRECTION            = 0x01
    I2USB_TXN_DIRECTION_WRITE       = 0x00
    I2USB_TXN_DIRECTION_READ        = 0x01
    I2USB_TXN_START                = 0x02
    I2USB_TXN_RESTART              = 0x04
    I2USB_TXN_STOP                 = 0x08
    I2USB_RESTART_HW               = 0x10
    I2USB_CONFIGURE                = 0x20
    I2USB_CONFIGURE_I2C_SPEED_1000  = 0x0C
    I2USB_CONFIGURE_I2C_SPEED_400   = 0x04
    I2USB_CONFIGURE_I2C_SPEED_100   = 0x00	
    I2USB_CONFIGURE_I2C_SPEED_050   = 0x08	
    I2USB_INTERFACE                = 0x0C
    # defined in AN2352, but unimplemented in favor of MGMT command below.
    I2USB_INTERFACE_I2C            = 0x00
    I2USB_INTERFACE_SPI            = 0x04
    I2USB_INTERFACE_UART           = 0x08
    I2USB_INTERFACE_LIN            = 0x0C

    # Management commands actually look like an i2c transfer with
    # a start condition, but have MSB set on slave address. Management
    # command opcode uses slave address LSBs. See mgmt().
    MGMT_GET_POWER_SETTING	 = 0x00
    MGMT_GET_KITPROG_VERSION = 0x01
    MGMT_RESET_KITPROG		 = 0x02
    MGMT_INTERFACE           = 0x0F
    MGMT_INTERFACE_I2C        = 0x00
    MGMT_INTERFACE_SWD        = 0x01
    MGMT_INTERFACE_NONE       = 0xff
    MGMT_ENTER_BOOTLOADER	 = 0x20

    CTRL_CMD_READ  = 0x01
    CTRL_CMD_WRITE = 0x02

    SWD_CMD_PROGRAM = 0x07

    SWD_CMD_BUFFER                = 0x00
    SWD_CMD_STATUS                = 0x01
    SWD_CMD_STATUS_POWER_DETECTED = 0x40
    SWD_CMD_RESET                 = 0x02
    SWD_CMD_SET_PROTOCOL          = 0x40
    SWD_CMD_SYNC                  = 0x41
    SWD_CMD_ACQUIRE               = 0x42
    SWD_CMD_SPECIAL               = 0x43

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
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    @classmethod
    def from_device(cls, d, pre):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, "%s-%s" % (pre, serial))

    @property
    def firmware_info(self):
        hw_version, minor, major = self.mgmt_get_version()
        
        return "KitProg v. %d.%d" % (major, minor)

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)

        self.device = device

    def i2usb_comm(self, control, length = 0, args = b'', rsize = 64):
        command = bytes([control, length]) + args
        self.bulk_out(self.EP_I2USB_OUT, command)
        data = self.bulk_in(self.EP_I2USB_IN, 64)[:rsize]
        self.logger.debug("-> %s", binascii.b2a_hex(data))
        return data

    def i2usb_freq_set(self, speed):
        if speed < 100e3:
            actual = 50e3
            cmd = self.I2USB_CONFIGURE | self.I2USB_CONFIGURE_I2C_SPEED_050
        elif speed < 400e3:
            actual = 100e3
            cmd = self.I2USB_CONFIGURE | self.I2USB_CONFIGURE_I2C_SPEED_100
        elif speed < 1000e3:
            actual = 400e3
            cmd = self.I2USB_CONFIGURE | self.I2USB_CONFIGURE_I2C_SPEED_400
        else:
            actual = 1000e3
            cmd = self.I2USB_CONFIGURE | self.I2USB_CONFIGURE_I2C_SPEED_1000

        self.i2usb_comm(cmd, rsize = 1)

        return actual

    def i2usb_hw_restart(self):
        return bool(self.i2usb_comm(self.I2USB_RESTART_HW, rsize = 1)[0])

    def i2usb_transfer(self, restart, stop, slave_addr, data_or_size):
        cmd = 0
        if restart:
            cmd |= self.I2USB_TXN_RESTART
        elif restart is False:
            cmd |= self.I2USB_TXN_START
        if stop:
            cmd |= self.I2USB_TXN_STOP
        if isinstance(data_or_size, int):
            cmd |= self.I2USB_TXN_DIRECTION_READ
            data = bytes([slave_addr])
            size = data_or_size
        else:
            cmd |= self.I2USB_TXN_DIRECTION_WRITE
            data = bytes([slave_addr]) + data_or_size
            size = len(data_or_size)
        self.logger.info("i2c cmd %02x size %d data %s rsize %d",
                         cmd, size, binascii.b2a_hex(data), size + 1)
        rdata = self.i2usb_comm(cmd, size, data, rsize = size + 1)
        saddr_ack = bool(rdata[0])
        if isinstance(data_or_size, int):
            return saddr_ack, rdata[1:]
        else:
            return saddr_ack, [bool(x) for x in rdata[1:]]

    def i2usb_stop(self):
        self.i2usb_transfer(None, True, 0, 0)

    def mgmt(self, command, args = b"", rsize = 0):
        blob = self.i2usb_comm(self.I2USB_TXN_START,
                               args = bytes([0x80 | command]) + args,
                               rsize = rsize + 1)
        ack = bool(blob[0] & 0x01)
        power = bool(blob[0] & 0x04)
        data = blob[1:]
        return ack, power, data

    def mgmt_get_power_settings(self):
        ack, power, data = self.mgmt(self.MGMT_GET_POWER_SETTING, rsize = 6)
        power_supply, i2c_speed, vtgt, vaux = struct.unpack("<BBHH", data[:6])
        return power, i2c_speed, vtgt, vaux

    def mgmt_get_version(self):
        ack, power, data = self.mgmt(self.MGMT_GET_KITPROG_VERSION, rsize = 3)
        hw_version, minor, major = data[:3]
        return hw_version, minor, major

    def mgmt_reset(self):
        ack, power, data = self.mgmt(self.MGMT_RESET_KITPROG)

    def mgmt_interface_set(self, intf):
        ack, power, data = self.mgmt(self.MGMT_INTERFACE, bytes([intf]))

    def mgmt_enter_bootloader(self):
        ack, power, data = self.mgmt(self.MGMT_ENTER_BOOTLOADER)

    def swd_cmd(self, write, cmd, mode, d0 = 0, d1 = 0, length = 0):
        return self.ctrl_in(self.CTRL_CMD_WRITE if write else self.CTRL_CMD_READ,
                            value = (mode << 8) | cmd,
                            index = (d1 << 8) | d0,
                            length = length)

    def swd_protocol_enable(self):
        return self.swd_cmd(write = True,
                            cmd = self.SWD_CMD_PROGRAM,
                            mode = self.SWD_CMD_SET_PROTOCOL,
                            d0 = self.MGMT_INTERFACE_SWD,
                            length = 1)[0]

    def swd_has_power(self):
        r = self.swd_cmd(write = False,
                         cmd = self.SWD_CMD_PROGRAM,
                         mode = self.SWD_CMD_STATUS,
                         length = 1)
        return r[0] == self.SWD_CMD_STATUS_POWER_DETECTED

    def swd_reset(self):
        self.swd_cmd(write = True,
                     cmd = self.SWD_CMD_PROGRAM,
                     mode = self.SWD_CMD_RESET)

    def swd_sync(self):
        self.swd_cmd(write = True,
                     cmd = self.SWD_CMD_PROGRAM,
                     mode = self.SWD_CMD_SYNC,
                     length = 1)

    def swd_unk(self):
        self.swd_cmd(write = True,
                     cmd = 4,
                     mode = 3,
                     length = 1)

    def swd_acquire(self):
        self.swd_cmd(write = True,
                     cmd = self.SWD_CMD_PROGRAM,
                     mode = self.SWD_CMD_ACQUIRE,
                     length = 1)

    def swd_special(self, op):
        self.swd_cmd(write = True,
                     cmd = self.SWD_CMD_PROGRAM,
                     mode = self.SWD_CMD_SPECIAL,
                     d0 = op,
                     length = 1)

    def swd_reset_bus(self):
        self.swd_special(op = 0)

    def swd_io(self, out_data, in_size, timeout = 1.0):
        writer = BackgroundWriter(self, self.EP_SWD_OUT, out_data, timeout)
        writer.start()
        try:
            return self.bulk_in(self.EP_SWD_IN, in_size, timeout)
        finally:
            writer.join(timeout)

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            raise NotImplementedError("Unsupported interface %s" % interface_name)

        if self.device.is_kernel_driver_active(0):
            self.device.detach_kernel_driver(0)

        if interface_name.lower() == "i2c":
            return I2cInterface(self)

        if interface_name.lower() == "swd":
            return SwdInterface(self)

        raise NotImplementedError("Unsupported interface %s" % interface_name)

class SwdInterface(swd.Interface):
    turnaround_supported = False

    def __init__(self, port):
        port.swd_sync()
        port.mgmt_get_version()
        port.mgmt_get_power_settings()
        port.swd_unk()
        port.swd_protocol_enable()
        port.swd_has_power()
        swd.Interface.__init__(self, port)

    @property
    def turnaround_cycles(self):
        return 1

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        if cycles != 1:
            raise NotImplementedError()    

    def cypress_line_reset(self):
        self.port.swd_acquire()
        op = swd.Read(0, self.IDCODE)
        self.execute([op])
        return op.data

    def flush(self, operations):
        if not operations:
            return

        pending = []
        rsize = 0

        for op in operations:
            pending.append(bytes([op.cmd]))
            rsize += 1
            if isinstance(op, swd.Write):
                pending.append(op.data.to_bytes(4, "little"))
            else:
                rsize += 4

        rsp = self.port.swd_io(b''.join(pending), rsize)

        off = 0
        for op in operations:
            if isinstance(op, swd.Read):
                op.data = int.from_bytes(rsp[off : off + 4], "little")
                off += 4
            status = rsp[off]
            op.ack = swd.Ack(status & 0x7)
            off += 1
            if isinstance(op, swd.Read) and status & 0x8:
                op.ack = swd.Ack.INVALID

    def _execute(self, operation_list):
        operation_list = list(operation_list)
        first = 0

        for i, op in enumerate(operation_list):
            if isinstance(op, (swd.Read, swd.Write)):
                continue

            self.flush(operation_list[first : i])
            first = i+1
            
            if isinstance(op, swd.Wakeup):
                self.port.swd_reset_bus()

            elif isinstance(op, swd.Run):
                pass

            elif isinstance(op, swd.JtagToSwd):
                self.port.swd_acquire()

            else:
                raise base.ProtocolError("Unknown SWD operation %s" % type(op))

        self.flush(operation_list[first:])

class I2cInterface(i2c.Interface):
    def __init__(self, port):
        i2c.Interface.__init__(self, port)

        self.logger.info("Version: %s", self.port.firmware_info)

        self.port.mgmt_interface_set(self.port.MGMT_INTERFACE_I2C)
        self.port.i2usb_freq_set(50e3)

    @property
    def freq(self):
        return self.__freq

    @freq.setter
    def freq(self, freq):
        self.__freq = self.port.i2usb_freq_set(freq)

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
                    saddr_ack, data = self.port.i2usb_transfer(None if as_prev else bool(prev),
                                                             not next and last_chunk,
                                                             cur.addr,
                                                             size)
                    if not saddr_ack:
                        self.port.i2usb_stop()
                        raise i2c.AddressNack()

                    cur.data += data
                    as_prev = True
            elif isinstance(cur, i2c.Write):
                for off in range(0, len(cur.data) or 1, 60):
                    size = min(len(cur.data) - off, 60)
                    last_chunk = off + size == len(cur.data)
                    chunk = cur.data[off : off + size]

                    saddr_ack, acks = self.port.i2usb_transfer(None if as_prev else bool(prev),
                                                             not next and last_chunk,
                                                             cur.addr,
                                                             chunk)
                    if not saddr_ack:
                        self.port.i2usb_stop()
                        raise i2c.AddressNack()
                    if not all(acks[:-1]):
                        self.port.i2usb_stop()
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
