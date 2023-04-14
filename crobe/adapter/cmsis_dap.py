from . import model
from ..protocol import swd
from .. import bitstring
from ..util.pretty import metric
from collections import deque
import usb.core
import usb.util
import time
import os
import math
import threading
import weakref
import errno

__all__ = []
                
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x0483, idProduct = 0x572a))
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x0483, idProduct = 0x5740))
class Adapter(model.Adapter):
    supported_interfaces = ["swd"]

    @classmethod
    def from_device(cls, d):
        serial = usb.util.get_string(d, d.iSerialNumber)
        return cls(d, "cmsis-dap-%s" % (serial))

    def __init__(self, device, name):
        model.Adapter.__init__(self, name)

        self.device = device
        cmsis = self.cmsis_interface_lookup()
        if not cmsis:
            raise RuntimeError("CMSIS-DAP interface not found")
        self.cmsis_dap_cfg_no, self.cmsis_dap_intf_no = cmsis
        self.cmsis_dap_intf = None

    def cmsis_interface_lookup(self):
        possible = []
        for config in self.device:
            for interface in config:
                if interface.iInterface == 0:
                    continue
                name = usb.util.get_string(self.device, interface.iInterface)
                precedence = {
                    "CMSIS-DAP": 10,
#                    "CMSIS-DAP v1 Adapter": 5,
                    "CMSIS-DAP v2 Adapter": 2,
                }.get(name, None)
                
                if precedence is None:
                    continue

                possible.append((precedence, config.bConfigurationValue, interface.bInterfaceNumber))

        if not possible:
            return

        if len(possible) > 1:
            possible.sort()

        selected = possible[0]
        return selected[1], selected[2]

    def cmsis_dap_out(self, data, timeout = None):
        data = bytes(data)
        self.logger.protocol("CD < %s", data.hex())
        self.device.write(self.cmsis_dap_ep_out.bEndpointAddress, data, int((timeout or 1.) * 1000))

    def cmsis_dap_in(self, timeout = None):
        self.logger.protocol("CD > ...")
        data = self.device.read(self.cmsis_dap_ep_in.bEndpointAddress, self.cmsis_dap_ep_in.wMaxPacketSize, int((timeout or 1.) * 1000))
        data = bytes(data)
        self.logger.protocol("-> %s", data.hex())
        return data

    def open(self, interface_name):
        if interface_name.lower() not in self.supported_interfaces:
            return None

        if self.cmsis_dap_intf is None:
            if self.device.is_kernel_driver_active(self.cmsis_dap_intf_no):
                self.device.detach_kernel_driver(self.cmsis_dap_intf_no)

            if self.device.get_active_configuration() != self.cmsis_dap_cfg_no:
                try:
                    self.device.set_configuration(self.cmsis_dap_cfg_no)
                    time.sleep(.5)
                except usb.core.USBError:
                    pass

            cfg = [cfg for cfg in self.device if cfg.bConfigurationValue == self.cmsis_dap_cfg_no][0]

            self.cmsis_dap_intf = [intf for intf in cfg if intf.bInterfaceNumber == self.cmsis_dap_intf_no][0]
            usb.util.claim_interface(self.device, self.cmsis_dap_intf)

            self.cmsis_dap_ep_in = usb.util.find_descriptor(
                self.cmsis_dap_intf,
                custom_match = lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress) ==
                usb.util.ENDPOINT_IN)
            self.cmsis_dap_ep_out = usb.util.find_descriptor(
                self.cmsis_dap_intf,
                custom_match = lambda e:
                usb.util.endpoint_direction(e.bEndpointAddress) ==
                usb.util.ENDPOINT_OUT)
            try:
                self.cmsis_dap_in(timeout = .1)
            except usb.core.USBError as e:
                if e.args[0] != errno.ETIMEDOUT:
                    raise
        
        if interface_name.lower() == "swd":
            return SwdInterface(self)

    def dap_cmd_execute(self, tx_data, rx_arg_len = 0, timeout = None):
        self.cmsis_dap_out(tx_data)
        time.sleep(.001)
        if rx_arg_len == 0:
            return
        for retry in range(3, -1, -1):
            rx_data = self.cmsis_dap_in(timeout = timeout)
            rx_op = rx_data[0]
            if rx_op == tx_data[0]:
                break
            if retry:
                continue
            raise RuntimeError("Bad response")
        if rx_arg_len is None:
            rx_len = rx_data[1]
            return rx_data[2 : 2 + rx_len]
        return rx_data[1 : 1 + rx_arg_len]

    def dap_info(self, identifier):
        return self.dap_cmd_execute(bytes([0x00, identifier]), rx_arg_len = None)

    def dap_info_string(self, no):
        return str(self.dap_info(no).rstrip(b'\x00'), "utf-8")

    def dap_info_int(self, no):
        return int.from_bytes(self.dap_info(no), "little")

    def dap_info_vendor_id(self):
        return self.dap_info_string(1)

    def dap_info_product_id(self):
        return self.dap_info_string(2)

    def dap_info_serial_number(self):
        return self.dap_info_string(3)

    def dap_info_cmsis_dap_fw_version(self):
        return self.dap_info_string(4)

    def dap_info_target_device_vendor(self):
        return self.dap_info_string(5)

    def dap_info_target_device_name(self):
        return self.dap_info_string(6)

    def dap_info_capabilities(self):
        info0, info1 = self.dap_info(0xf0)
        return info0, info1

    def dap_info_test_domain_timer(self):
        return self.dap_info_int(0xf1)

    def dap_info_swo_trace_buffer_size(self):
        return self.dap_info_int(0xfd)

    def dap_info_packet_count(self):
        return self.dap_info_int(0xfe)

    def dap_info_packet_size(self):
        return self.dap_info_int(0xff)

    def dap_host_status(self, type, status):
        rsp = self.dap_cmd_execute(bytes([0x01, type, status]), rx_arg_len = 1)
        if rsp[0] != 0x00:
            raise ValueError(rsp)

    def dap_connect(self, port):
        rsp = self.dap_cmd_execute(bytes([0x02, port]), rx_arg_len = 1)
        if rsp[0] != port:
            raise ValueError(rsp)

    def dap_disconnect(self):
        rsp = self.dap_cmd_execute(bytes([0x03]), rx_arg_len = 1)
        return rsp[0]

    def dap_write_abort(self, dap, abort):
        rsp = self.dap_cmd_execute(bytes([0x08, dap]) + abort.to_bytes(4, "little"), rx_arg_len = 1)
        return rsp[0]

    def dap_delay(self, us):
        rsp = self.dap_cmd_execute(bytes([0x09]) + delay.to_bytes(2, "little"), rx_arg_len = 1)
        return rsp[0]

    def dap_reset_target(self):
        rsp = self.dap_cmd_execute(bytes([0x0a]), rx_arg_len = 2)
        return rsp[0], rsp[1]

    def dap_swj_pins(self, output, select, wait):
        rsp = self.dap_cmd_execute(bytes([0x10, output, select]) + wait.to_bytes(4, "little"), rx_arg_len = 1)
        return rsp[0]

    def dap_swj_clock(self, clock):
        rsp = self.dap_cmd_execute(bytes([0x11]) + clock.to_bytes(4, "little"), rx_arg_len = 1)
        return rsp[0]

    def dap_swj_sequence(self, bs):
        assert len(bs) <= 256
        if len(bs) == 0:
            return
        l = len(bs)
        if l == 256:
            l = 0
        rsp = self.dap_cmd_execute(bytes([0x12, l]) + bytes(bs), rx_arg_len = 1)
        return rsp[0]

    def dap_swd_configure(self, configuration):
        rsp = self.dap_cmd_execute(bytes([0x13, configuration]), rx_arg_len = 1)
        return rsp[0]

    def dap_swd_sequence(self, count_or_bs):
        blob = b""
        count = 0
        rx_size = 1

        for o in count_or_bs:
            if isinstance(o, int):
                assert o <= 64
                count += 1
                blob += bytes([(o & 0x3f) | 0x80])
                rx_size += (o + 7) // 8
            else:
                assert len(o) <= 64
                count += 1
                blob += bytes([len(o) & 0x3f]) + bytes(o)

        rsp = self.dap_cmd_execute(bytes([0x1d, count]) + blob, rx_arg_len = rx_size)
        rx_data = []
        point = 1
        for o in count_or_bs:
            if isinstance(o, int):
                size = (o + 7) // 8
                rx_data.append(bitstring.BitString(rx_data[point : point + size], o))
                point += size
            else:
                rx_data.append(None)
        return rsp[0], rx_data

    def dap_jtag_sequence(self, sequences):
        raise NotImplementedError()

    def dap_jtag_configure(self):
        raise NotImplementedError()

    def dap_jtag_idcode(self):
        raise NotImplementedError()

    def dap_transfer_configure(self, idle_cycles, wait_retry, match_retry):
        rsp = self.dap_cmd_execute(bytes([0x04, idle_cycles]) + wait_retry.to_bytes(2, "little") + match_retry.to_bytes(2, "little"), rx_arg_len = 1)
        return rsp[0]

    def _dap_transfer(self, dap_index, transfers):
        count = 0
        commands = []
        rx_arg_len = 2

        for tr in transfers:
            count += 1
            c, r = tr.to_cmd_rsp()
            tr.__point = rx_arg_len
            tr.__len = r
            rx_arg_len += r
            commands.append(c)

        cmd_blob = b''.join(commands)
        rsp = self.dap_cmd_execute(bytes([0x05, dap_index, count]) + cmd_blob, rx_arg_len = rx_arg_len)

        ack = rsp[1]
        if ack & 0x4:
            ack = swd.Ack.PARITY_ERR
        else:
            ack = swd.Ack(ack & 0x7)

        for tr in transfers:
            response = rsp[tr.__point : tr.__point + tr.__len]
            tr.handle_rsp(ack, response)
    
    def dap_transfer(self, dap_index, transfers):
        max_size = self.cmsis_dap_ep_in.wMaxPacketSize - 3 - 5

        pending = []
        tx_size = 0
        rx_size = 0
        for i, tr in enumerate(transfers):
            last = i == len(transfers) - 1

            pending.append(tr)
            c, r = tr.cmd_rsp_size()
            tx_size += c
            rx_size += c
            if tx_size >= max_size or rx_size >= max_size or last:
                self._dap_transfer(dap_index, pending)
                pending = []

        assert not pending

    def dap_transfer_block(self):
        raise NotImplementedError()

    def dap_transfer_abort(self):
        self.cmsis_dap_out(b"\x07")
        
class DapTransfer:
    def __init__(self, op):
        self.op = op

    def cmd_rsp_size(self):
        if isinstance(self.op, swd.Read):
            return 1, 4
        else:
            return 5, 0
        
    def to_cmd_rsp(self):
        if isinstance(self.op, swd.Read):
            cmd = bytes([self.op.ap | 2 | ((self.op.addr & 3) << 2)])
            return cmd, 4
        else:
            cmd = bytes([self.op.ap | ((self.op.addr & 3) << 2)]) + int(self.op.data).to_bytes(4, "little")
            return cmd, 0

    def handle_rsp(self, ack, blob):
        self.op.ack = ack
        if isinstance(self.op, swd.Read):
            self.op.data = int.from_bytes(blob, "little")

class SwdInterface(swd.Interface):
    access_method = "register"

    def __init__(self, port):
        self.__frequency = 1e6
        self.__frequency_dirty = True
        self.__turnaround = 1
        self.__turnaround_dirty = True
        super().__init__(port)
        self.port.dap_connect(1)
        self.freq_cap("user", 1e6)

    @property
    def turnaround_cycles(self):
        return self.__turnaround

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        if self.__turnaround == cycles:
            return
        self.__turnaround_dirty = True
        self.__turnaround = cycles

    def freq_update(self, freq):
        self.__frequency = freq or 1e6
        self.__frequency_dirty = True
        return self.__frequency

    def _execute(self, operation_list):
        transfer_queue = []

        if self.__frequency_dirty:
            self.__frequency_dirty = False
            self.port.dap_swj_clock(int(self.__frequency))

        if self.__turnaround_dirty:
            self.__turnaround_dirty = False
            self.port.dap_swd_configure(((self.__turnaround - 1) & 3) | 4)
        
        for i, op in enumerate(operation_list):
            if isinstance(op, swd.Wakeup):
                if transfer_queue:
                    self.port.dap_transfer(0, transfer_queue)
                    transfer_queue = []

                self.port.dap_swd_sequence([bitstring.BitString(-1, 64)])

            elif isinstance(op, swd.SelectionOperation):
                if transfer_queue:
                    self.port.dap_transfer(0, transfer_queue)
                    transfer_queue = []

                parts = []
                for off in range(0, len(op.out), 64):
                    parts.append(op.out[off : min(len(op.out), off + 64)])
                self.port.dap_swd_sequence(parts)

            elif isinstance(op, swd.Run):
                if transfer_queue:
                    self.port.dap_transfer(0, transfer_queue)
                    transfer_queue = []

                parts = []
                c = op.cycles + 1
                for off in range(0, c, 64):
                    parts.append(bitstring.BitString(0, min(c - off, 64)))
                self.port.dap_swd_sequence(parts)

            elif isinstance(op, (swd.Read, swd.Write)):
                transfer_queue.append(DapTransfer(op))

            else:
                raise base.ProtocolError("Unknown SWD operation %s" % type(op))

        if transfer_queue:
            self.port.dap_transfer(0, transfer_queue)
            transfer_queue = []
