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

__all__ = []

class BackgroundReader(threading.Thread):
    def __init__(self, owner, ep):
        super().__init__()
        self.logger = owner.logger
        self.device = owner.device
        self.ep = ep
        self.running = 3
        self.rx_buffer = b''
        self.data_exclusive = threading.Condition()
        self.start()
        weakref.finalize(owner, self.stop)

    def stop(self):
        self.running = False
        self.join()
        
    def run(self):
        while self.running:
            try:
                data = self.device.read(self.ep.bEndpointAddress, self.ep.wMaxPacketSize, 500)
            except usb.core.USBTimeoutError:
                self.running -= 1
                data = None
            self.rx_handle(data)

    def rx_handle(self, data):
        if data is None:
            self.logger.protocol("RX/async --")
            return
        with self.data_exclusive:
            data = bytes(data)
            self.logger.protocol("RX/async > %s", data.hex())
            self.rx_buffer += data
            self.data_exclusive.notify_all()

    def flush(self):
        with self.data_exclusive:
            self.rx_buffer = b''

    def read(self, size = None, timeout = None):
        while True:
            with self.data_exclusive:
                self.running = 3
                self.logger.protocol("CD > %s %s...", size, timeout)
                if size is None and self.rx_buffer:
                    t = self.rx_buffer
                    self.rx_buffer = b''
                    self.logger.protocol("> %s", t.hex())
                    return t
                if len(self.rx_buffer) >= size:
                    t = self.rx_buffer[:size]
                    self.rx_buffer = self.rx_buffer[size:]
                    self.logger.protocol("> %s", t.hex())
                    return t
                self.data_exclusive.wait(timeout = timeout)
                
@model.UsbEnumerator.db.register(model.UsbInfo(idVendor = 0x0483, idProduct = 0x572a))
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
        for config in self.device:
            for interface in config:
                if interface.iInterface == 0:
                    continue
                if usb.util.get_string(self.device, interface.iInterface) != "CMSIS-DAP":
                    continue

                return config.bConfigurationValue, interface.bInterfaceNumber
        return None

    def cmsis_dap_out(self, data, timeout = None):
        data = bytes(data)
        self.logger.protocol("CD < %s", data.hex())
        self.device.write(self.cmsis_dap_ep_out.bEndpointAddress, data, int((timeout or 1.) * 1000))

#    def cmsis_dap_in(self, size, timeout = None):
#        self.logger.protocol("CD > %d", size)
#        data = self.device.read(self.cmsis_dap_ep_in.bEndpointAddress, size, int((timeout or 1.) * 1000))
#        data = bytes(data)
#        self.logger.protocol("-> %s", data.hex())
#        return data

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

            self.cmsis_dap_reader = BackgroundReader(self, self.cmsis_dap_ep_in)
        
        if interface_name.lower() == "swd":
            return SwdInterface(self)

    def dap_cmd_execute(self, tx_data, rx_size = None, timeout = None):
        self.cmsis_dap_reader.flush()
        self.cmsis_dap_out(tx_data)
        return self.cmsis_dap_reader.read(rx_size, timeout = timeout)

    def dap_info(self, identifier):
        rsp, len = self.dap_cmd_execute(bytes([0x00, identifier]), rx_size = 2)
        if rsp != 0:
            raise RuntimeError("Bad response")
        return self.cmsis_dap_reader.read(len)

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
        rsp = self.dap_cmd_execute(bytes([0x01, type, status]), 2)
        if rsp != b'\x01\x00':
            raise ValueError(rsp)

    def dap_connect(self, port):
        rsp = self.dap_cmd_execute(bytes([0x02, port]), 2)
        if rsp[0] != 0x02 or rsp[1] != port:
            raise ValueError(rsp)

    def dap_disconnect(self):
        rsp = self.dap_cmd_execute(bytes([0x03]), 2)
        if rsp[0] != 0x03:
            raise ValueError(rsp)
        return rsp[1]

    def dap_write_abort(self, dap, abort):
        rsp = self.dap_cmd_execute(bytes([0x08, dap]) + abort.to_bytes(4, "little"), 2)
        if rsp[0] != 0x08:
            raise ValueError(rsp)
        return rsp[1]

    def dap_delay(self, us):
        rsp = self.dap_cmd_execute(bytes([0x09]) + delay.to_bytes(2, "little"), 2)
        if rsp[0] != 0x09:
            raise ValueError(rsp)
        return rsp[1]

    def dap_reset_target(self):
        rsp = self.dap_cmd_execute(bytes([0x0a]), 3)
        if rsp[0] != 0x0a:
            raise ValueError(rsp)
        return rsp[1], rsp[2]

    def dap_swj_pins(self, output, select, wait):
        rsp = self.dap_cmd_execute(bytes([0x10, output, select]) + wait.to_bytes(4, "little"), 2)
        if rsp[0] != 0x10:
            raise ValueError(rsp)
        return rsp[1]

    def dap_swj_clock(self, clock):
        rsp = self.dap_cmd_execute(bytes([0x11]) + wait.to_bytes(4, "little"), 2)
        if rsp[0] != 0x11:
            raise ValueError(rsp)
        return rsp[1]

    def dap_swj_sequence(self, bs):
        assert len(bs) <= 256
        if len(bs) == 0:
            return
        l = len(bs)
        if l == 256:
            l = 0
        rsp = self.dap_cmd_execute(bytes([0x12, l]) + bytes(bs), 2)
        if rsp[0] != 0x12:
            raise ValueError(rsp)
        return rsp[1]

    def dap_swd_configure(self, configuration):
        rsp = self.dap_cmd_execute(bytes([0x13, configuration]), 2)
        if rsp[0] != 0x13:
            raise ValueError(rsp)
        return rsp[1]

    def dap_swd_sequence(self, count_or_bs):
        blob = b""
        count = 0
        rx_size = 2

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

        rsp = self.dap_cmd_execute(bytes([0x1d, count]) + blob, rx_size)
        if rsp[0] != 0x1d:
            raise ValueError(rsp)
        rx_data = []
        point = 2
        for o in count_or_bs:
            if isinstance(o, int):
                size = (o + 7) // 8
                rx_data.append(bitstring.BitString(rx_data[point : point + size], o))
                point += size
            else:
                rx_data.append(None)
        return rsp[1], rx_data

    def dap_jtag_sequence(self, sequences):
        raise NotImplementedError()

    def dap_jtag_configure(self):
        raise NotImplementedError()

    def dap_jtag_idcode(self):
        raise NotImplementedError()

    def dap_transfer_configure(self, idle_cycles, wait_retry, match_retry):
        rsp = self.dap_cmd_execute(bytes([0x04, idle_cycles]) + wait_retry.to_bytes(2, "little") + match_retry.to_bytes(2, "little"), 2)
        if rsp[0] != 0x04:
            raise ValueError(rsp)
        return rsp[1]

    def dap_transfer(self, dap_index, req_data):
        cmd = []
        count = 0
        rx_size = 0
        for r in req_data:
            count += 1
            request = r[0]
            if request & 0x30 or (request & 0x2) == 0:
                cmd.append(bytes([request]) + r[1].to_bytes(4, "little"))
            else:
                cmd.append(bytes([request]))
            rx_size += 1
            if request & 0x02:
                rx_size += 4
            if request & 0x80:
                rx_size += 4
        blob = b''.join(cmd)

        rsp = self.dap_cmd_execute(bytes([0x05, dap_index, count]) + blob, 2 + rx_size)
        if rsp[0] != 0x05:
            raise ValueError(rsp)
        #if rsp[1] != count:
        #    raise ValueError(rsp)

        responses = []
        point = 2
        for r in req_data:
            count += 1
            request = r[0]
            response = rsp[point]
            point += 1
            ts = None
            data = None
            if request & 0x80:
                ts = int.from_bytes(rsp[point : point + 4], "little")
                point += 4
            if request & 0x02:
                data = int.from_bytes(rsp[point : point + 4], "little")
                point += 4
            responses.append((response, data, ts))
        return responses

    def dap_transfer_block(self):
        raise NotImplementedError()

    def dap_transfer_abort(self):
        self.cmsis_dap_out(b"\x07")
        
class SwdInterface(swd.Interface):
    access_method = "register"

    def __init__(self, port):
        super().__init__(port)
        self.port.dap_connect(1)

    turnaround_supported = False
        
    @property
    def turnaround_cycles(self):
        return 1

    @turnaround_cycles.setter
    def turnaround_cycles(self, cycles):
        pass

    def freq_update(self, freq):
        return freq or 1e3

    def _execute(self, operation_list):
        for i, op in enumerate(operation_list):
            if isinstance(op, swd.Wakeup):
                self.port.dap_swd_sequence([bitstring.BitString(-1, 64)])

            elif isinstance(op, swd.SelectionOperation):
                parts = []
                for off in range(0, len(op.out), 64):
                    parts.append(op.out[off : min(len(op.out), off + 64)])
                self.port.dap_swd_sequence(parts)

            elif isinstance(op, swd.Run):
                parts = []
                c = op.cycles + 1
                for off in range(0, c, 64):
                    parts.append(bitstring.BitString(0, min(c - off, 64)))
                self.port.dap_swd_sequence(parts)

            elif isinstance(op, swd.Read):
                rsp = self.port.dap_transfer(0, [(op.ap | 2 | ((op.addr & 3) << 2), None)])
                ack, data, ts = rsp[0]
                op.data = data
                if ack & 0x4:
                    op.ack = swd.Ack.PARITY_ERR
                else:
                    op.ack = swd.Ack(ack & 0x7)
            elif isinstance(op, swd.Write):
                rsp = self.port.dap_transfer(0, [(op.ap | ((op.addr & 3) << 2), op.data)])
                ack, data, ts = rsp[0]
                op.data = data
                if ack & 0x4:
                    op.ack = swd.Ack.PARITY_ERR
                else:
                    op.ack = swd.Ack(ack & 0x7)

            else:
                raise base.ProtocolError("Unknown SWD operation %s" % type(op))
