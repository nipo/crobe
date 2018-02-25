from .model import Component
from .component.model import Cpu, Register
from .loadable.object import Program, Segment
from .util.allocator import Allocator
import time
import binascii
import struct

class Zone(object):
    def __init__(self, bus, r):
        self.range = r
        self.bus = bus

    @property
    def address(self):
        return self.range.address

    @property
    def end(self):
        return self.range.end

    @property
    def size(self):
        return self.range.size
        
    def write(self, blob, offset = 0):
        if offset + len(blob) > self.size:
            raise ValueError("Blob does not fit the zone")
        self.bus.mem_write(self.address + offset, blob)

    def read(self, size, offset = 0):
        if offset + size > self.size:
            raise ValueError("Addresses do not fit the zone")
        return self.bus.mem_read(self.address + offset, size)

class Puppet(Component):
    def __init__(self, cpu, ram,
                 pc_reg, sp_reg,
                 arg_regs, trampoline_code,
                 stack_size = 128, stack_direction = -1):
        Component.__init__(self, "puppet")
        self.cpu = cpu
        self.ram = ram
        self.ram_allocator = Allocator(ram.address, ram.size)
        self.pc_reg = pc_reg
        self.sp_reg = sp_reg
        self.arg_regs = arg_regs
        self.stack = self.allocate(stack_size)
        if stack_direction < 0:
            self.stack_init = self.stack.end - 8
        else:
            self.stack_init = self.stack.address
        self.trampoline = self.allocate(len(trampoline_code) + 4)
        self.trampoline_code = trampoline_code

        self.logger.info("ready, trampoline at 0x%08x", self.trampoline.address)
        
    def allocate(self, size, align = 1):
        return Zone(self.cpu.bus, self.ram_allocator.allocate(size, align))
        
    def unallocate(self, zone):
        self.ram_allocator.free(zone.range)

    def prepare(self, pc, *args):
        assert self.cpu.state != self.cpu.State.RUN
        assert len(args) <= len(self.arg_regs)

        regs = {
            self.sp_reg: self.stack_init,
            self.pc_reg: self.trampoline.address,
        }

        for r, v in zip(self.arg_regs, args):
            regs[r] = v

        tc = self.trampoline_code + struct.pack("<L", pc)
        self.trampoline.write(tc)
        self.cpu.reg_write(regs)

    def run(self):
        self.cpu.resume(allow_interrupts = False)

    def step(self):
        self.cpu.step()
        
    def wait(self, max_time = .05):
        deadline = time.time() + max_time
        while self.cpu.state == self.cpu.State.RUN and time.time() < deadline:
            pass

        self.logger.debug("state %s reason %s", self.cpu.state, self.cpu.halt_cause)

        if self.cpu.state == self.cpu.State.RUN:
            self.cpu.halt()
            self.logger.warning("Forced stop of target")

        #regs = self.cpu.reg_read(self.cpu.registers)
        #for r, v in sorted(regs.items()):
        #    self.logger.info("After stop %s: 0x%08x", r.name, v)
            
    def call(self, pc, *args):
        self.prepare(pc, *args)
        self.run()
        self.wait()
        r0 = self.arg_regs[0]
        return self.cpu.reg_read([r0])[r0]

