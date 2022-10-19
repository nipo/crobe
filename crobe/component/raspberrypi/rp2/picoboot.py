from ....adapter import model
from ....protocol import spi
from ....model import PortComponent
import usb.core
import usb.util
import binascii
import struct
import time
import enum
import os

__all__ = []

class Status(enum.IntEnum):
    Ok                    = 0
    UnknownCmd            = 1
    InvalidCmdLength      = 2
    InvalidTransferLength = 3
    InvalidAddress        = 4
    BadAlignment          = 5
    InterleavedWrite      = 6
    Rebooting             = 7
    UnknownError          = 8

class Command(enum.IntEnum):
    ExclusiveAccess = 0x01
    Reboot          = 0x02
    FlashErase      = 0x03
    Read            = 0x84
    Write           = 0x05
    ExitXip         = 0x06
    EnterCmdXip     = 0x07
    Exec            = 0x08
    VectorizeFlash  = 0x09

class InterfaceControl(enum.IntEnum):
    Reset = 0x41
    Status = 0x42
    
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x2e8a, idProduct = 0x0003))
class PicoBoot(model.Adapter):
    supported_interfaces = ["picoboot", "spi"]

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, f"rp2-{serial}")

    def __init__(self, device, name):
        super().__init__(name)
        self.handle = device

    def open(self, interface_name):
        if interface_name == "picoboot":
            boot = BootInterface(self.handle)
            self.child_add(boot)
            return boot
        if interface_name == "spi":
            boot = BootInterface(self.handle)
            spi = SpiPassthrough(boot)
            return spi

class BootInterface(PortComponent):
    ROM_BASE = 0x00000000
    XIP_BASE = 0x10000000
    SRAM_BASE = 0x20000000
    RAW_EXEC_BASE = SRAM_BASE

    devices = {
        0x0100: ("RP2040", 256*1024, 0),
    }

    def __init__(self, handle):
        super().__init__(handle, "picoboot")
        self.last_token = 0

        cfg = self.port.get_active_configuration()
        if cfg.bConfigurationValue == 0:
            self.port.set_configuration(1)
            cfg = self.port.get_active_configuration()
        for intf in cfg:
            self.logger.debug("Has interface %d, %02x:%02x:%02x",
                  intf.index,
                  intf.bInterfaceClass,
                  intf.bInterfaceSubClass,
                  intf.bInterfaceProtocol)
            if intf.bInterfaceClass == 0xff \
               and intf.bInterfaceSubClass == 0x00 \
               and intf.bInterfaceProtocol == 0x00:
                self.intf = intf
                break
        usb.util.claim_interface(self.port, self.intf)

        self.ep_in = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            self.intf,
            custom_match = lambda e:
            usb.util.endpoint_direction(e.bEndpointAddress) ==
            usb.util.ENDPOINT_OUT)
    
        self.device_name, self.ram_size, self.flash_size = \
            self.devices[handle.bcdDevice]
        
    def boot_control(self, request, value, data_or_wLength, timeout = 1000):
        self.logger.protocol("Boot ctrl %02x %04x %s", request, value, data_or_wLength.hex() if isinstance(data_or_wLength, bytes) else data_or_wLength)
        return self.port.ctrl_transfer(
            (0x80 if isinstance(data_or_wLength, int) else 0) | 0x41,
            bRequest = int(request),
            wValue = value, wIndex = self.intf.index,
            data_or_wLength = data_or_wLength,
            timeout = timeout)

    def boot_out(self, data, timeout = 1000):
        chunk_size = self.ep_out.wMaxPacketSize
        for off in range(0, len(data), chunk_size):
            chunk = data[off : off + chunk_size]
            self.logger.protocol("Boot < %s", chunk.hex())
            self.port.write(self.ep_out.bEndpointAddress, chunk, timeout)
        if len(data) == 0:
            self.logger.protocol("Boot < -")
            self.port.write(self.ep_out.bEndpointAddress, b'', timeout)

    def boot_in(self, timeout = 1000):
        self.logger.protocol("Boot > ?")
        ret = self.port.read(self.ep_in.bEndpointAddress, self.ep_in.wMaxPacketSize,
                             timeout)
        ret = bytes(ret)
        self.logger.protocol("     > %s", ret.hex())
        return ret
        
    def boot_reset(self):
        self.boot_control(InterfaceControl.Reset, 0, b'', 1000)

    def boot_cmd_status(self):
        rsp = self.boot_control(InterfaceControl.Status, 0, 16, 1000)
        token, statuscode, id, progress, pad = struct.unpack("<LLBB6s", rsp)
        status = Status(statuscode)
        return token, status, id, progress

    def command_execute(self, cmd, data_or_len = None):
        cmd_token = int.from_bytes(cmd[4:8], "little")

        try:
            self.boot_out(cmd)
            if cmd[8] & 0x80:
                data_or_len = data_or_len or 0
                rdata = b''
                while len(rdata) < data_or_len:
                    chunk = self.boot_in()
                    rdata += chunk
                    if len(chunk) < self.ep_in.wMaxPacketSize:
                        break
                self.boot_out(b'')
                return rdata

            else:
                data_or_len = data_or_len or b''
                if data_or_len:
                    self.boot_out(data_or_len)
                self.boot_in()
                return
        except usb.core.USBError:
            pass
        token, status, id, progress = self.boot_cmd_status()
        self.boot_reset()
        raise RuntimeError(status)

    def cmd_serialize(self, cmd, transfer_length, fmt = "", *args):
        self.logger.debug("command %s %s %s trx %d", cmd, fmt, ['%#010x'%x for x in args], transfer_length)
        MAGIC = 0x431fd10b
        self.last_token += 1
        arg_size = struct.calcsize(fmt)
        cmd = struct.pack("<LLBBHL",
                          MAGIC,
                          self.last_token,
                          int(cmd), arg_size,
                          0,
                          transfer_length)
        cmd += struct.pack(fmt, *args)
        cmd += b'\x00' * (16 - arg_size)
        return cmd
        
    def exclusive_access(self, exclusive):
        self.logger.debug("exclusive %d", exclusive)
        cmd = self.cmd_serialize(Command.ExclusiveAccess, 0, "<B", exclusive)
        return self.command_execute(cmd)

    def exit_xip(self):
        self.logger.debug("exit_xip")
        cmd = self.cmd_serialize(Command.ExitXip, 0)
        return self.command_execute(cmd)

    def enter_cmd_xip(self):
        self.logger.debug("enter_cmd_xip")
        cmd = self.cmd_serialize(Command.EnterCmdXip, 0)
        return self.command_execute(cmd)

    def reboot(self, pc, sp, delay_ms):
        self.logger.debug("reboot %#010x %#010x %d", pc, sp, delay_ms)
        cmd = self.cmd_serialize(Command.Reboot, 0, "<LLL", pc, sp, delay_ms)
        return self.command_execute(cmd)

    def exec(self, addr):
        self.logger.debug("exec %#010x", addr)
        cmd = self.cmd_serialize(Command.Exec, 0, "<L", addr | 1)
        return self.command_execute(cmd)

    def flash_erase(self, addr, size):
        self.logger.debug("flash_erase %#010x %d", addr, size)
        assert addr % 4096 == 0, "Must be page-aligned"
        assert size % 4096 == 0, "Must be page-aligned"
        cmd = self.cmd_serialize(Command.FlashErase, 0, "<LL", addr, size)
        return self.command_execute(cmd)

    def vectorize_flash(self, addr):
        self.logger.debug("vectorize_flash")
        cmd = self.cmd_serialize(Command.VectorizeFlash, 0, "<L", addr)
        return self.command_execute(cmd)

    def write(self, addr, data):
        if not data:
            return
        self.logger.debug("write %#010x %s", addr, data.hex())
        if addr & 0xff000000 == 0x10000000:
            assert addr % 256 == 0, "Must be page-aligned"
        cmd = self.cmd_serialize(Command.Write, len(data), "<LL", addr, len(data))
        return self.command_execute(cmd, data)

    def read(self, addr, size):
        if not size:
            return b''
        self.logger.debug("read %#010x %d", addr, size)
        cmd = self.cmd_serialize(Command.Read, size, "<LL", addr, size)
        return self.command_execute(cmd, size)

    def poke(self, addr, data):
        self.logger.debug("poke %#010x %#010x", addr, data)
        POKE_CMD = bytes([0x01, 0x48, 0x02, 0x49,
                          0x08, 0x60, 0x70, 0x47])
        poke_blob = POKE_CMD + struct.pack("<LL", data, addr)
        self.write(self.RAW_EXEC_BASE, poke_blob)
        return self.exec(self.RAW_EXEC_BASE)

    def peek(self, addr):
        self.logger.debug("peek %#010x", addr)
        PEEK_CMD = bytes([0x02, 0x48, 0x00, 0x68,
                          0x79, 0x46, 0x48, 0x60,
                          0x70, 0x47, 0xc0, 0x46])
        peek_blob = PEEK_CMD + struct.pack("<L", addr)
        self.write(self.RAW_EXEC_BASE, peek_blob)
        self.exec(self.RAW_EXEC_BASE)
        data_blob = self.read(self.RAW_EXEC_BASE + len(peek_blob), 4)
        return int.from_bytes(data_blob, "little")

class SpiPassthrough(spi.Interface):
    def __init__(self, boot_interface):
        super().__init__(boot_interface, "spi")
        self.interface = boot_interface
        self.child_add(spi.Target(self, "cs0", 0))

    def start(self):
        super().start()
        self.interface.boot_reset()
        self.interface.exit_xip()

    def _execute(self, operation_list):
        parts = []

        self.logger.protocol("Running %s", operation_list)

        for op in operation_list:
            if isinstance(op, spi.Cs):
                parts.append((None, None, 0x80000000 if op.value is not None else 0x80000001))

            elif isinstance(op, spi.Shift) and isinstance(op.mosi, int) and op.read_miso:
                # Read-only
                parts.append((None, op, op.mosi))

            elif isinstance(op, spi.Shift) and not isinstance(op.mosi, int) and op.read_miso:
                # Read/write
                parts.append((op.mosi, op, len(op.mosi)))

            elif isinstance(op, spi.Shift) and not isinstance(op.mosi, int) and not op.read_miso:
                # Write-only
                parts.append((op.mosi, None, len(op.mosi)))

            else:
                raise NotImplementedError(op)

        rxd = self.transaction_run(parts)
        for (mosi, op, count), data in zip(parts, rxd):
            if op:
                op.miso = data

    def transaction_run(self, parts):
        from .bootloader_kernels import rp2040

        function_code = rp2040["flash_spi_transact"]
        marker = (0xdeadbee0).to_bytes(4, "little")
        to_patch = function_code.index(marker)

        ptr = self.interface.RAW_EXEC_BASE
        base_addr = ptr
        ptr += len(function_code)

        self.logger.debug("%#010x: %s", base_addr, function_code.hex())
        
        cmd_buffer_addr = ptr
        ptr += 12 * (len(parts) + 1)
        cmd_buffer = b""

        tx_blobs = b''.join([tx_data for (tx_data, r, c) in parts if tx_data])
        tx_ptr = ptr
        ptr += len(tx_blobs)
        rx_base = ptr
        rx_size = 0

        for tx_data, do_rx, count in parts:
            part = struct.pack("<LLL",
                               tx_ptr if tx_data else 0,
                               ptr if do_rx else 0,
                               count)
            self.logger.debug("%#010x: %s", cmd_buffer_addr + len(cmd_buffer),
                             part.hex())
            cmd_buffer += part
            if tx_data:
                self.logger.debug("%#010x: %s", tx_ptr, tx_data.hex())
                tx_ptr += count

            if do_rx:
                self.logger.debug("%#010x: pending rx", ptr)
                ptr += count
                rx_size += count
        self.logger.debug("%#010x: %s", cmd_buffer_addr + len(cmd_buffer),
                         (b'\x00'*12).hex())

        blob = function_code[:to_patch] \
            + cmd_buffer_addr.to_bytes(4, "little") \
            + function_code[to_patch+4:] \
            + cmd_buffer \
            + b'\x00'*12 \
            + tx_blobs
        for off in range(0, len(blob), 16):
            self.logger.debug("%#010x: %s", base_addr+off, blob[off:][:16].hex())

        self.interface.write(base_addr, blob)
        self.interface.exec(base_addr)
        rx_blobs = self.interface.read(rx_base, rx_size)

        ret = []
        ptr = 0
        for rx_data, do_rx, count in parts:
            if do_rx:
                ret.append(rx_blobs[ptr : ptr + count])
                ptr += count
            else:
                ret.append(None)
        return ret
