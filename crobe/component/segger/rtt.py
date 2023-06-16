import threading
import time
from ...model import PortComponent
from ...protocol import pipe, base
from ...component.arm import dp
import struct

class Channel(PortComponent):
    def __init__(self, port, index, is_write = False):
        super().__init__(port, f"{'w' if is_write else 'r'}{index}")
        self.is_write = is_write
        self.is_active = False
        self.reset()

    def reset(self):
        self.is_active = False
        self.address = None
        self.name_address = None
        self.channel_name = None
        self.buffer_address = None
        self.buffer_size = None
        self.read_ptr = None
        self.write_ptr = None
        self.flags = None
        
    def address_set(self, address):
        """
        Sets a new base address, returns whether channel changed
        """
        if self.address == address:
            return False
        
        self.is_active = address is not None
        self.address = address
        if self.address:
            return self.refresh()
        else:
            self.reset()
            return True
        
    def refresh(self):
        """
        Refreshes channel info, returns whether channel changed (excluding
        normal data exchange)
        """
        if not self.is_active:
            return False

        blob = self.port.port.mem_read(self.address, 24)
        name_address, buffer_address, buffer_size, write_ptr, read_ptr, flags = struct.unpack("<LLLLLL", blob)
        changed = False

        changed = changed or (name_address != self.name_address)
        changed = changed or (buffer_address != self.buffer_address)
        changed = changed or (buffer_size != self.buffer_size)

        self.name_address = name_address
        self.buffer_address = buffer_address
        self.buffer_size = buffer_size
        
        if changed or self.channel_name is None:
            channel_name = self.string_fetch(name_address)
            changed = changed or (channel_name != self.channel_name)
            self.channel_name = channel_name

        if not self.is_write:
            changed = changed or (self.write_ptr != write_ptr)
        else:
            changed = changed or (self.read_ptr != read_ptr)

        self.write_ptr = write_ptr
        self.read_ptr = read_ptr

        if changed:
            self.logger.info("Buffer block changed, name=%s, %d bytes ptrs: %d %d", self.channel_name, self.buffer_size,
                             self.write_ptr, self.read_ptr)

        return changed

    def buffer_read(self, size = None):
        """
        Read from buffer, returns a blob of at most size bytes
        """
        if not self.is_active:
            return b''
        
        if size is None:
            size = self.buffer_size

        if self.read_ptr <= self.write_ptr:
            available = self.write_ptr - self.read_ptr
        else:
            available = self.buffer_size - self.read_ptr + self.write_ptr

        to_transfer = min(size, available)
        if to_transfer <= 0:
            return b''

        blob = self.port.port.mem_read(self.buffer_address + self.read_ptr, min(self.buffer_size - self.read_ptr, to_transfer))
        if self.read_ptr <= self.write_ptr and len(blob) < to_transfer:
            blob += self.port.port.mem_read(self.buffer_address, to_transfer - len(blob))
        self.read_ptr += to_transfer
        self.read_ptr %= self.buffer_size
        self.port.port.mem_write(self.address + 16, struct.pack("<L", self.read_ptr))
        return blob

    def buffer_write(self, data):
        """
        Writes to buffer, returns effective size written
        """
        if not self.is_active or not data:
            return len(data)

        if self.write_ptr <= self.read_ptr:
            available = self.read_ptr - self.write_ptr
        else:
            available = self.buffer_size - self.write_ptr + self.read_ptr

        to_transfer = min(len(data), available)
        if to_transfer <= 0:
            return 0

        to_transfer0 = min(self.buffer_size - self.write_ptr, to_transfer)
        self.port.port.mem_write(self.buffer_address + self.write_ptr, data[:to_transfer0])
        if self.write_ptr <= self.read_ptr and to_transfer0 < to_transfer:
            self.port.port.mem_write(self.buffer_address, data[to_transfer0:to_transfer])
        self.write_ptr += to_transfer
        self.write_ptr %= self.buffer_size
        self.port.port.mem_write(self.address + 16, struct.pack("<L", self.write_ptr))
        return to_transfer

    def string_fetch(self, address, max_size = 64):
        """
        Retrieves a NUL-terminated string from memory at address, with a
        limit if NUL is not found.
        """
        if address == 0:
            return ""

        data = b''
        while b"\0" not in data and len(data) < max_size:
            try:
                data += self.port.port.mem_read(address + len(data), min(max_size - len(data), 16))
            except:
                break
        return str(data.split(b"\0")[0], "utf-8", "ignore")
    
class Control(PortComponent):
    TAG = b"SEGGER RTT"

    def __init__(self, port):
        super().__init__(port, "control")
        self.scan_range = None
        self.address = None
        self.is_active = False
        self.tx_channel_count = 0
        self.rx_channel_count = 0
        self.tx_channel = [Channel(self, index, False) for index in range(16)]
        self.rx_channel = [Channel(self, index, True) for index in range(16)]

    def address_scan(self, begin, end):
        self.logger.debug("Scanning control block in %010x:%010x", begin, end)
        tags = [self.TAG[i:i+4] for i in range(0, 8, 4)]
        for address in range(begin, end, 8):
            marker = self.port.mem_read(address, 4)
            self.logger.debug("At %#010x, marker %s", address, marker.hex())
            if marker in tags:
                address_to_try = address - tags.index(marker) * 4
                tag = self.port.mem_read(address_to_try, 16)
                if tag[:len(self.TAG)] == self.TAG:
                    self.logger.info("Found control block at %010x", address_to_try)
                    return address_to_try 
       
    def scan_range_set(self, address):
        if self.scan_range == address:
            return False

        self.reset()
        self.address = None
        self.scan_range = address
        return self.refresh()

    def reset(self):
        for channel in self.tx_channel:
            channel.address_set(None)
        for channel in self.rx_channel:
            channel.address_set(None)
        self.tx_channel_count = 0
        self.rx_channel_count = 0
        self.is_active = False
        return True
        
    def refresh(self):
        if self.scan_range is None and self.address is not None:
            self.address = None
            self.reset()
            self.logger.info("RTT control lost")
            return True

        if self.scan_range and (not self.is_active or self.address is None):
            address = self.address_scan(self.scan_range.start, self.scan_range.stop)
            if address is None:
                return False
            self.logger.info("RTT control found by scanning at %#010x", address)
            self.address = address

        if not self.address:
            return False
            
        tag_count = self.port.mem_read(self.address, 24)
        tag, tx_count, rx_count = struct.unpack("<16sLL", tag_count)
        if tag[:len(self.TAG)] != self.TAG:
            self.address = None
            return self.reset()

        changed = False
        if not self.is_active:
            changed = True

        changed = changed or (self.tx_channel_count != tx_count)
        changed = changed or (self.rx_channel_count != rx_count)

        if not changed:
            for channel in self.tx_channel[:self.tx_channel_count]:
                channel.refresh()
            for channel in self.rx_channel[:self.rx_channel_count]:
                channel.refresh()
            return False

        self.logger.info("Control block changed, %d tx, %d rx", tx_count, rx_count)

        self.reset()

        if tx_count >= 32 or rx_count >= 32:
            return

        self.is_active = True
        self.tx_channel_count = min(tx_count, 16)
        self.rx_channel_count = min(rx_count, 16)
            
        for index, channel in enumerate(self.tx_channel[:self.tx_channel_count]):
            channel.address_set(self.address + 24 + index * 24)
        for index, channel in enumerate(self.rx_channel[:self.rx_channel_count]):
            channel.address_set(self.address + 24 + (index + tx_count) * 24)

        return changed

    def pair_get(self, index):
        if index >= 16:
            return None, None
        return self.tx_channel[index], self.rx_channel[index]
    
class Rtt(PortComponent):
    def __init__(self, port):
        PortComponent.__init__(self, port, "rtt")
        self.address_set(None)
        self.port_count = 0
        self.control = Control(self.port)

        for i in range(16):
            tx, rx = self.control.pair_get(i)
            self.child_add(RttPort(self, i, tx, rx))

    def address_set(self, address):
        if isinstance(address, str):
            if ":" in value:
                begin, end = address.split(":", 1)
                self.scan_range = range(int(begin, 16) & ~3, int(end, 16) & ~3)
            else:
                address = int(value, 16)
                self.scan_range = range(address & ~3, (address + 4) & ~3)
        elif isinstance(address, int):
            self.scan_range = range(address & ~3, (address + 4) & ~3)
        elif isinstance(address, range):
            self.scan_range = range(address.start & ~3, address.stop)
        elif address is None:
            self.scan_range = None
        else:
            raise ValueError(address)
        
    def option_set(self, option):
        if option.startswith("addr"):
            _, value = option.split("=", 1)
            self.address_set(value)
            return
        return super().option_set(option)

    def start(self):
        super().start()

        self.thread = RunnerThread(self)
        self.thread.start()

    def do_poll(self):
        self.control.scan_range_set(self.scan_range)
        self.control.refresh()

        if not self.control.is_active:
            return

        for p in self.children:
            p.poll()
        
class RunnerThread(threading.Thread):
    def __init__(self, rtt, interval = .1):
        self.rtt = rtt
        super().__init__()
        self.running = False
        self.interval = interval

    def start(self):
        self.running = True
        super().start()

    def stop(self):
        self.running = False

    def run(self):
        while self.running:
            begin = time.time()
            try:
                self.rtt.do_poll()
            except dp.DpAccessFailure:
                pass
            to_next = self.interval - (time.time() - begin)
            if to_next > 0:
                time.sleep(to_next)

class RttPort(pipe.Interface):
    def __init__(self, port, index, from_rtt, to_rtt):
        super().__init__(port, f"channel{index}")
        self.to_rtt = to_rtt
        self.from_rtt = from_rtt
        self.to_rtt_buffer = b""
        self.from_rtt_buffer = b""

    def poll(self):
        self.from_rtt_buffer += self.from_rtt.buffer_read()
        written = self.to_rtt.buffer_write(self.to_rtt_buffer)
        self.to_rtt_buffer = self.to_rtt_buffer[written:]
        
    def execute(self, operation_list, timeout = None):
        for op in operation_list:
            if isinstance(op, pipe.Read):
                to_pop = min(len(self.from_rtt_buffer), op.size)
                op.data = self.from_rtt_buffer[:to_pop]
                self.from_rtt_buffer = self.from_rtt_buffer[to_pop:]

            elif isinstance(op, pipe.Write):
                self.to_rtt_buffer += op.data

            elif isinstance(op, base.Reset):
                pass

            else:
                raise ValueError(op)
