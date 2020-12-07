import re
import socket
from ...model import PortComponent
from ...protocol import spi
from ... import bitstring
import enum
import time

class RegisterAddress(enum.IntEnum):
    Mode = 0
    Gateway = 1
    Subnet = 5
    SrcMacAddr = 9
    SrcIpAddr = 0xf
    Interrupt = 0x15
    InterruptMask = 0x16
    RetryTime = 0x17
    RetryCount = 0x19
    RxMemorySize = 0x1a
    TxMemorySize = 0x1b
    PPPoEAuthType = 0x1c
    PPPLcpReqTimer = 0x28
    PPPLcpMagic = 0x29
    UnreachableIpAddr = 0x2a
    UnreachablePort = 0x2e

    Socket0 = 0x400
    Socket1 = 0x500
    Socket2 = 0x600
    Socket3 = 0x700

    TxMemBase = 0x4000
    RxMemBase = 0x6000
    
class SocketRegister(enum.IntEnum):
    Mode = 0x0
    Command = 0x1
    Interrupt = 0x2
    Status = 0x3
    SrcPort = 0x4
    DstMacAddr = 0x6
    DstIpAddr = 0xc
    DstPort = 0x10
    Mss = 0x12
    Proto = 0x14
    Tos = 0x15
    Ttl = 0x16
    TxFree = 0x20
    TxReadPtr = 0x22
    TxWritePtr = 0x24
    RxSize = 0x26
    RxReadPtr = 0x28

class SocketCommand(enum.IntEnum):
    Idle = 0
    Open = 1
    Listen = 2
    Connect = 4
    Disconnect = 8
    Close = 0x10
    Send = 0x20
    SendMac = 0x21
    SendKeep = 0x22
    Recv = 0x40

class SocketStatus(enum.IntEnum):
    Closed = 0
    Init = 0x13
    Listen = 0x14
    Established = 0x17
    CloseWait = 0x1c
    Udp = 0x22
    IpRaw = 0x32
    MacRaw = 0x42
    Pppoe = 0x5f
    SynSent = 0x15
    SynRecv = 0x16
    FinWait = 0x18
    Closing = 0x1a
    TimeWait = 0x1b
    LastAck = 0x1d
    Arp = 1

class SocketStatus(enum.IntEnum):
    Closed = 0
    Init = 0x13
    Listen = 0x14
    Established = 0x17
    CloseWait = 0x1c
    Udp = 0x22
    IpRaw = 0x32
    MacRaw = 0x42
    Pppoe = 0x5f
    SynSent = 0x15
    SynRecv = 0x16
    FinWait = 0x18
    Closing = 0x1a
    TimeWait = 0x1b
    LastAck = 0x1d
    Arp = 1

class SocketIrq(enum.IntFlag):
    Con = 1
    Discon = 2
    Recv = 4
    Timeout = 8
    SendOk = 0x10

@spi.Target.db.register("w5100")
class W5100(PortComponent):
    def __init__(self, port):
        super().__init__(port, "w5100")

    def _read(self, addr):
        cmd = self.port.cmd_shift(b'\x0f' + int(addr).to_bytes(2, "big") + b'\xff', read_miso = True)
        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])
        assert cmd.miso[:3] == b'\x00\x01\x02'
        return cmd.miso[3]

    def _write(self, addr, value):
        cmd = self.port.cmd_shift(b'\xf0' + int(addr).to_bytes(2, "big") + bytes([value]), read_miso = True)
        self.port.execute([self.port.cmd_cs(True), cmd, self.port.cmd_cs(False)])
        assert cmd.miso == b'\x00\x01\x02\x03', cmd.miso

    def multi_read(self, base, size):
        return bytes([self._read(base + i) for i in range(size)])

    def multi_write(self, base, data):
        for off, v in enumerate(data):
            self._write(base + off, v)

    @classmethod
    def reg_name(cls, reg):
        if int(reg) < 0x100:
            return RegisterAddress(reg).name
        if RegisterAddress.Socket0 <= reg < RegisterAddress.Socket0 + 0x400:
            n = (reg >> 8) & 3
            r = SocketRegister(reg & 0xff)
            return f"Socket{n}.{r.name}"
        if RegisterAddress.TxMemBase <= reg < RegisterAddress.RxMemBase:
            return f"TxMem[{reg-RegisterAddress.TxMemBase:#06x}]"
        if RegisterAddress.RxMemBase <= reg:
            return f"RxMem[{reg-RegisterAddress.RxMemBase:#06x}]"

    def mem_write(self, base, data):
        self.logger.debug("Writing %s: %s", self.reg_name(base), data.hex())
        self.multi_write(base, data)

    def mem_read(self, base, size):
        self.logger.debug("Reading %s", self.reg_name(base))
        r = self.multi_read(base, size)
        self.logger.debug("-> %s", r.hex())
        return r
        
    def reg8_write(self, reg, val):
        self.logger.debug("Writing %s: %s (0x%02x)", self.reg_name(reg), val, val)
        self.multi_write(reg, bytes([val]))

    def reg8_read(self, reg):
        self.logger.debug("Reading %s", self.reg_name(reg))
        r = self.multi_read(reg, 1)[0]
        self.logger.debug("-> 0x%02x", r)
        return r

    def reg16_write(self, reg, val):
        self.logger.debug("Writing %s: %s (0x%02x)", self.reg_name(reg), val, val)
        self.multi_write(reg, int(val).to_bytes(2, "big"))

    def reg16_read(self, reg):
        self.logger.debug("Reading %s", self.reg_name(reg))
        r = int.from_bytes(self.multi_read(reg, 2), "big")
        self.logger.debug("-> 0x%02x", r)
        return r

    @classmethod
    def ip_to_data(cls, text):
        return socket.inet_aton(text)

    @classmethod
    def ip_from_data(cls, data):
        return socket.inet_ntoa(data)

    _mac_byte = re.compile(r'[a-fA-F0-9][a-fA-F0-9]')
    @classmethod
    def mac_to_data(cls, text):
        return bytes(int(x, 16) for x in cls._mac_byte.findall(text))

    @classmethod
    def mac_from_data(cls, data):
        return ':'.join(f'{b:02x}' for b in data)
    
    def ip_write(self, reg, val):
        self.logger.debug("Writing %s: '%s'", self.reg_name(reg), val)
        self.multi_write(reg, self.ip_to_data(val))

    def ip_read(self, reg):
        self.logger.debug("Reading %s", self.reg_name(reg))
        r = self.ip_from_data(self.multi_read(reg, 4))
        self.logger.debug("-> '%s'", r)
        return r

    def mac_write(self, reg, val):
        self.logger.debug("Writing %s: '%s'", self.reg_name(reg), val)
        self.multi_write(reg, self.mac_to_data(val))

    def mac_read(self, reg):
        self.logger.debug("Reading %s", self.reg_name(reg))
        r = self.mac_from_data(self.multi_read(reg, 6))
        self.logger.debug("-> '%s'", r)
        return r

    def irq_get(self):
        return Irq(self.reg8_read(RegisterAddress.Interrupt))
    
    def init(self):
        self.reg8_write(RegisterAddress.Mode, 0x80)
        while self.reg8_read(RegisterAddress.Mode) & 0x80:
            time.sleep(.1)
        self.reg8_write(RegisterAddress.Mode, 0x10)
        self.reg8_read(RegisterAddress.Mode)
        self.ip_write(RegisterAddress.Gateway, "10.0.100.254")
        self.ip_read(RegisterAddress.Gateway)
        self.ip_write(RegisterAddress.Subnet, "255.255.255.0")
        self.ip_write(RegisterAddress.SrcIpAddr, "10.0.100.142")
        self.mac_write(RegisterAddress.SrcMacAddr, "02:44:55:66:77:88")
        self.reg16_write(RegisterAddress.RetryTime, 2000)
        self.reg8_write(RegisterAddress.RetryCount, 3)
        self.reg8_write(RegisterAddress.RxMemorySize, 0x55)
        self.reg8_write(RegisterAddress.TxMemorySize, 0x55)

        s0 = Socket(self, 0,
                    RegisterAddress.TxMemBase, 2048,
                    RegisterAddress.RxMemBase, 2048)
        s0.udp_init(1234)
        s0.udp_packet_tx("10.0.100.4", 3334, b"Hello\n")
        while not s0.is_send_complete():
            time.sleep(.1)

        s0.close()

        s0.tcp_init(4444)
        s0.tcp_connect("10.0.100.4", 22)
        s0.tcp_connect_wait()
        s0.data_write(b"GET / HTTP/1.1\r\nHost: ouazo.local\r\nConnection: close\r\n\r\n", exact = True)
        s0.cmd_set(SocketCommand.Send)
        while True:
            if s0.has_irq(SocketIrq.Recv):
                d = s0.data_read()
                s0.recv()
                print(d)
            if s0.has_irq(SocketIrq.Discon):
                break
        s0.close()

        s0.tcp_init(4444)
        s0.tcp_listen()
        s0.tcp_connect_wait()
        while True:
            d = None
            if s0.has_irq(SocketIrq.Recv):
                d = s0.data_read()
                if d is not None:
                    s0.recv()
                    print(d)
            if s0.has_irq(SocketIrq.Discon):
                break
            if d is not None:
                s0.data_write(d[::-1])
                s0.send()
        s0.close()

class Socket(PortComponent):
    def __init__(self, port, no, tx_base, tx_size, rx_base, rx_size):
        self.no = no
        self.reg_base = self.no * 0x100 + 0x400
        self.rx_base = rx_base
        self.tx_base = tx_base
        self.rx_size = rx_size
        self.tx_size = tx_size
        super().__init__(port, f"Socket{no}")
        self.reg16_write(SocketRegister.TxFree, self.tx_size)
        self.reg16_write(SocketRegister.TxReadPtr, 0)
        self.reg16_write(SocketRegister.TxWritePtr, 0)
        self.reg16_write(SocketRegister.RxSize, 0)
        self.reg16_write(SocketRegister.RxReadPtr, 0)

    def reg_addr(self, no):
        return no + self.reg_base
        
    def mem_write(self, reg, val):
        self.port.mem_write(self.reg_addr(reg), val)

    def mem_read(self, reg, size):
        return self.port.mem_read(self.reg_addr(reg), size)

    def reg8_write(self, reg, val):
        self.port.reg8_write(self.reg_addr(reg), val)

    def reg8_read(self, reg):
        return self.port.reg8_read(self.reg_addr(reg))

    def reg16_write(self, reg, val):
        self.port.reg16_write(self.reg_addr(reg), val)

    def reg16_read(self, reg):
        return self.port.reg16_read(self.reg_addr(reg))

    def ip_write(self, reg, val):
        self.port.ip_write(self.reg_addr(reg), val)

    def ip_read(self, reg):
        return self.port.ip_read(self.reg_addr(reg))

    def mac_write(self, reg, val):
        self.port.mac_write(self.reg_addr(reg), val)

    def mac_read(self, reg):
        return self.port.mac_read(self.reg_addr(reg))

    def data_peek(self, size = 2**16):
        available = self.reg16_read(SocketRegister.RxSize)
        offset = self.reg16_read(SocketRegister.RxReadPtr) & (self.rx_size - 1)
        chunk0_size = min(self.rx_size - offset, available, size)
        if not chunk0_size:
            return b''
        chunk1_size = available - self.rx_size
        received = self.port.mem_read(self.rx_base + offset, chunk0_size)
        if chunk1_size:
            received += self.port.mem_read(0, chunk1_size)
        return received

    def data_read(self, size = 2**16, exact = False):
        self.irq_clear(SocketIrq.Recv)
        available = self.reg16_read(SocketRegister.RxSize)
        rptr = self.reg16_read(SocketRegister.RxReadPtr)
        offset = rptr & (self.rx_size - 1)
        chunk0_size = min(self.rx_size - offset, available, size)
        if not chunk0_size:
            return b''
        if available < size and exact:
            return None
        chunk1_size = available - self.rx_size
        received = self.port.mem_read(self.rx_base + offset, chunk0_size)
        if chunk1_size:
            received += self.port.mem_read(0, chunk1_size)
        self.reg16_write(SocketRegister.RxReadPtr, (rptr + available) & 0xffff)
        return received

    def data_write(self, data, exact = False):
        self.irq_clear(SocketIrq.SendOk)
        available = self.reg16_read(SocketRegister.TxFree)
        if not available:
            return 0
        if exact and available < len(data):
            return 0

        wptr = self.reg16_read(SocketRegister.TxWritePtr)
        offset = wptr & (self.tx_size - 1)
        chunk_size = min(self.tx_size - offset, len(data), available)
        self.port.mem_write(self.tx_base + offset, data[:chunk_size])
        data = data[chunk_size:]
        self.reg16_write(SocketRegister.TxWritePtr, (wptr + chunk_size) & 0xffff)
        self.reg16_read(SocketRegister.TxReadPtr)
        self.reg16_read(SocketRegister.TxWritePtr)
        self.reg16_read(SocketRegister.TxFree)
        return chunk_size

    def tcp_init(self, port):
        self.reg8_write(SocketRegister.Mode, 0x01)
        self.reg16_write(SocketRegister.SrcPort, port)
        self.cmd_set(SocketCommand.Open)
        if self.reg8_read(SocketRegister.Status) != SocketStatus.Init:
            self.cmd_set(SocketCommand.Close)
            raise RuntimeError("Cannot init TCP Server socket")

    def tcp_connect(self, host, port):
        self.ip_write(SocketRegister.DstIpAddr, host)
        self.reg16_write(SocketRegister.DstPort, port)
        self.irq_clear(SocketIrq.Con | SocketIrq.Discon | SocketIrq.Timeout)
        self.cmd_set(SocketCommand.Connect)

    def tcp_listen(self):
        self.irq_clear(SocketIrq.Con | SocketIrq.Discon | SocketIrq.Timeout)
        self.cmd_set(SocketCommand.Listen)

    def tcp_connect_wait(self):
        while True:
            irq = self.irq_get()
            if irq & SocketIrq.Con:
                break
            if irq & SocketIrq.Discon:
                raise RuntimeError("Connection failed")
            if irq & SocketIrq.Timeout:
                raise RuntimeError("Connection timeout")
            time.sleep(.1)
            continue

    def tcp_close(self):
        while True:
            irq = self.irq_get()
            if irq & SocketIrq.Con:
                break
            if irq & SocketIrq.Discon:
                raise RuntimeError("Connection failed")
            if irq & SocketIrq.Timeout:
                raise RuntimeError("Connection timeout")
            time.sleep(.01)
            continue

    def udp_init(self, port):
        self.reg8_write(SocketRegister.Mode, 0x02)
        self.reg16_write(SocketRegister.SrcPort, port)
        self.cmd_set(SocketCommand.Open)
        if self.reg8_read(SocketRegister.Status) != SocketStatus.Udp:
            self.cmd_set(SocketCommand.Close)
            raise RuntimeError("Cannot init UDP socket")

    def udp_packet_rx(self):
        if not self.has_irq(SocketIrq.Recv):
            return None
        header = self.data_peek(8)
        if len(header) < 8:
            return None
        ip = header[:4]
        port = int.from_bytes(header[4:6], "big")
        size = int.from_bytes(header[6:8], "big")
        frame = self.data_read(8 + size, exact = True)
        if not frame:
            return None
        return W5100.ip_from_data(ip), port, frame[8:]

    def udp_packet_tx(self, ip, port, data):
        self.ip_write(SocketRegister.DstIpAddr, ip)
        #self.mac_write(SocketRegister.DstMacAddr, "0c:4d:e9:bf:23:18")
        self.reg16_write(SocketRegister.DstPort, port)
        written = self.data_write(data, exact = True)
        if not written:
            raise RuntimeError("Cannot write frame")
        self.send()
        
    def is_send_complete(self):
        return self.cmd_get() != SocketCommand.Close

    def close(self):
        self.cmd_set(SocketCommand.Close)
        self.irq_clear(0xff)

    def irq_get(self):
        return SocketIrq(self.reg8_read(SocketRegister.Interrupt))

    def cmd_get(self):
        return SocketCommand(self.reg8_read(SocketRegister.Command))

    def cmd_set(self, val):
        return self.reg8_write(SocketRegister.Command, val)

    def has_irq(self, val):
        return self.irq_get() & val

    def irq_clear(self, val):
        return self.reg8_write(SocketRegister.Interrupt, val)

    def send(self):
        self.cmd_set(SocketCommand.Send)

    def recv(self):
        self.cmd_set(SocketCommand.Recv)
