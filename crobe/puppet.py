from .model import Component
from .component.model import Cpu, Register
from .loadable.object import Program, Segment
from .util.allocator import Allocator
import time
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
        assert offset + len(blob) <= self.size
        self.bus.mem_write(self.address + offset, blob)

    def read(self, size, offset = 0):
        assert offset + size <= self.size
        return self.bus.mem_read(self.address + offset, size)
        
class Puppet(Component):
    def __init__(self, cpu, ram,
                 pc_reg, sp_reg, lr_reg,
                 arg_regs, trampoline_code,
                 stack_size = 1024, stack_direction = -1):
        Component.__init__(self, "puppet")
        self.cpu = cpu
        self.ram = ram
        self.ram_allocator = Allocator(ram.address, ram.size)
        self.pc_reg = pc_reg
        self.sp_reg = sp_reg
        self.lr_reg = lr_reg
        self.arg_regs = arg_regs
        self.stack = self.allocate(stack_size)
        if stack_direction < 0:
            self.stack_init = self.stack.end
        else:
            self.stack_init = self.stack.address
        self.trampoline = self.allocate(len(trampoline_code) + 4)
        self.trampoline_code = trampoline_code

        self.logger.info("ready")
        
    def allocate(self, size):
        return Zone(self.cpu.bus, self.ram_allocator.allocate(size))
        
    def unallocate(self, zone):
        self.ram_allocator.free(zone.range)

    def prepare(self, pc, *args):
        self.logger.debug("CPU State: %s", self.cpu.state)

        assert self.cpu.state != self.cpu.State.RUN
        assert len(args) <= len(self.arg_regs)

        regs = {
            self.sp_reg: self.stack_init,
            self.pc_reg: self.trampoline.address,
        }

        for r, v in zip(self.arg_regs, args):
            regs[r] = v

        self.trampoline.write(self.trampoline_code + struct.pack("<L", pc))

        for r, v in sorted(regs.items()):
            self.logger.debug("Setting %s: 0x%08x", r.name, v)

        self.cpu.reg_write(regs)

        self.logger.debug("Running code trampoline at 0x%08x, target PC 0x%08x", self.trampoline.address, pc)
        self.logger.debug("Registers before run:")

        regs = self.cpu.reg_read(self.cpu.registers)
        for r, v in sorted(regs.items()):
            self.logger.debug(" %s: 0x%08x", r.name, v)

    def run(self):
        self.cpu.resume(allow_interrupts = False)
        self.logger.debug("CPU State: %s", self.cpu.state)

    def step(self):
        self.cpu.step()
        poll_regs = [self.pc_reg, self.lr_reg, self.sp_reg] + self.arg_regs
        regs = self.cpu.reg_read(poll_regs)
        self.logger.debug(", ".join(["%s: 0x%08x" % (r.name, value) for (r, value) in sorted(regs.items())]))
        
    def wait(self, interval = .01):
        self.logger.debug("Waiting for CPU to stop...")

        poll_regs = [self.pc_reg, self.lr_reg, self.sp_reg] + self.arg_regs

        tries = 20
        while self.cpu.state == self.cpu.State.RUN and tries:
            regs = self.cpu.reg_read(poll_regs)
            self.logger.debug(", ".join(["%s: 0x%08x" % (r.name, value) for (r, value) in sorted(regs.items())]))
            time.sleep(interval)
            tries -= 1

        self.cpu.halt()

        self.logger.debug("Done, registers after run:")
        regs = self.cpu.reg_read(self.cpu.registers)
        for r, v in sorted(regs.items()):
            self.logger.debug(" %s: 0x%08x", r.name, v)
        
