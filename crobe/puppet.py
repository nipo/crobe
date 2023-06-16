from .model import Component, PortComponent
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

class Puppet(PortComponent):
    def __init__(self, soc, cpu, ram,
                 pc_reg, sp_reg,
                 arg_regs, trampoline_code,
                 stack_size = 128, stack_direction = -1):
        super().__init__(soc, "puppet")
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

        self.logger.debug("ready, trampoline at 0x%08x", self.trampoline.address)
        
    def allocate(self, size, align = 1):
        return Zone(self.cpu.bus, self.ram_allocator.allocate(size, align))
        
    def unallocate(self, zone):
        self.ram_allocator.free(zone.range)

    def prepare(self, pc, *args):
        self.logger.trace("Preparing 0x%08x(%s)", pc, ', '.join(hex(a) for a in args))

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
        st = self.cpu.state
        hc = self.cpu.halt_cause
        self.logger.trace("Starting CPU, current state: %s, halt cause %s", st, hc)
        self.cpu.resume(allow_interrupts = False)

    def step(self):
        self.cpu.step()
        
    def wait(self, timeout = None):
        deadline = time.time() + (timeout or .2)
        while self.cpu.state == self.cpu.State.RUN and time.time() < deadline:
            pass

        st = self.cpu.state
        hc = self.cpu.halt_cause

        dump = False
        if st == self.cpu.State.RUN:
            self.cpu.halt()
            self.logger.error("Forced stop of target")
            dump = True

        if st in [self.cpu.State.LOCKUP, self.cpu.State.FAULT]:
            self.logger.error("CPU ended up in bad state")
            dump = True

        if dump:
            self.logger.debug("State %s reason %s", st, hc)
            regs = self.cpu.reg_read(self.cpu.registers)
            for r, v in sorted(regs.items()):
                self.logger.debug("After stop %s: 0x%08x", r.name, v)

        r0 = self.arg_regs[0]
        return self.cpu.reg_read([r0])[r0]

    def call(self, pc, *args, timeout = None):
        self.prepare(pc, *args)
        self.run()
        return self.wait(timeout = timeout)

