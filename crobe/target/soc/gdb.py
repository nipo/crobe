from ...gdb import protocol, message
import binascii
from ...memory import region
from ...component.model import Cpu, Register, Bus
from xml.etree import ElementTree as et

class Responder(protocol.Responder):
    def __init__(self, socket, soc):
        self.soc = soc
        self.cpus = soc.children_of_class(Cpu)
        self.cpu = self.cpus[0]
        self.cur_thread_id = 1
        protocol.Responder.__init__(self, socket, self.cpu.gdb_byteorder, self.cpu.gdb_feature_name)
        self.symbols_to_resolve.append('rtt_control')
        
    def memory_map_xml(self):
        mm = et.Element("memory-map")
        regions = self.soc.children_of_class(region.Region)
        for r in regions:
            if r.type not in (region.Type.RAM, region.Type.FLASH):
                continue
            el = et.SubElement(mm, "memory",
                               type = r.type.name.lower(),
                               start = hex(r.address),
                               length = hex(r.size))
            if r.type == region.Type.FLASH:
                et.SubElement(el, "property",
                              name = "blocksize").text = hex(r.page_size)

        return b'<?xml version="1.0"?>' \
            + b'<!DOCTYPE memory-map PUBLIC "+//IDN gnu.org//DTD GDB Memory Map V1.0//EN"' \
            + b' "http://sourceware.org/gdb/gdb-memory-map.dtd">' \
            + et.tostring(mm)
    
    def memory_read(self, addr, size):
        return self.cpus[0].bus.mem_read(addr, size)

    def memory_write(self, addr, blob):
        pass


    def monitor_youpi(self, command, args):
        """Test monitor command"""
        self.respond(message.Ok())
    
    def flash_erase(self, addr, size):
        regions = self.soc.children_of_class(region.Region)
        for r in regions:
            if not isinstance(r, region.Flash):
                continue

            if r.address <= addr and addr + size <= r.address + r.size:
                r.erase(addr, size)
            
    def flash(self, program):
        regions = self.soc.children_of_class(region.Region)
        for r in regions:
            if not isinstance(r, region.Flash):
                continue

            pages = program.within(r.address, r.address + r.size)
            r.write(pages)

    def thread_ids(self):
        return range(1, len(self.cpus))
    
    def thread_select(self, id):
        if id <= 0:
            self.cpu = self.cpus[0]
            self.cur_thread_id = 1
        else:
            self.cpu = self.cpus[id - 1]
            self.cur_thread_id = id

    def reset(self):
        self.cpu.reset()

    def step(self):
        self.cpu.step()

    def resume(self):
        self.cpu.resume()

    def halt(self):
        self.cpu.halt()

    @property
    def run_state(self):
        return self.cpu.state

    @property
    def halt_cause(self):
        return self.cpu.halt_cause
    
    @property
    def registers(self):
        return self.cpu.registers

    def reg_set(self, registers):
        self.cpu.reg_write(registers)

    def reg_get(self, registers):
        return self.cpu.reg_read(registers)
