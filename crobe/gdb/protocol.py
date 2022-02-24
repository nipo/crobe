from .message import *
from ..loadable.object import Segment, Program
from .server import Session
import logging
import binascii
import re
from ..component.model import Cpu, Register, Bus
from xml.etree import ElementTree as et

class Responder(Session):
    def __init__(self, socket, endianness, feature_name):
        Session.__init__(self, socket)
        self.logger = logging.getLogger("gdb")
        self.endianness = endianness
        self.feature_name = feature_name
        self.features = []
        self.features.append("QStartNoAckMode+")
        self.features.append("PacketSize=4000")

        target = et.Element("target")
        regs = et.SubElement(target, 'feature', name = self.feature_name)

        for r in self.registers:
            t, g = self.REGTYPE_MAP[r.datatype]
            et.SubElement(regs, "reg",
                          name = r.name,
                          bitsize = str(r.width),
                          regnum = str(r.number),
                          type = t,
                          group = g)

        self.__target_xml = b'' \
                            + b'<?xml version="1.0"?>' \
                            + b'<!DOCTYPE feature SYSTEM "gdb-target.dtd">' \
                            + et.tostring(target)

        self.features.append("qXfer:features:read+")
        
        mm = self.memory_map_xml()
        if mm:
            self.__memorymap_xml = mm
            self.features.append("qXfer:memory-map:read+")

        self.symbols_to_resolve = []
        self.symbol = {}

    REGTYPE_MAP = {
        Register.Type.GPR: ('int', 'general'),
        Register.Type.FLOAT: ('float', 'float'),
        Register.Type.DOUBLE: ('ieee_double', 'float'),
        Register.Type.PC: ('code_ptr', 'general'),
        Register.Type.LR: ('code_ptr', 'general'),
        Register.Type.SP: ('data_ptr', 'general'),
        Register.Type.SYSTEM: ('int', 'general'),
        }

    def handle_interrupt(self):
        self.logger.trace("Interrupt requested")

    remapped = {
        '?': 'question',
        '!': 'bang',
        }
        
    def handle(self, command):
        assert isinstance(command, Command)

        self.logger.protocol("Command: %s", command.data)

        cmd = str(command.data[:1], 'ascii')
        cmd = self.remapped.get(cmd, cmd)

        handler = getattr(self, "handle_" + cmd, self.handle_unknown)

        try:
            handler(command)
        except Exception:
            self.logger.exception("Command handling failed")
            self.respond(Error(42))

    def respond(self, response):
        self.logger.protocol("Response: %s", response.data)
        Session.respond(self, response)
            
    def handle_unknown(self, command, *args):
        self.logger.warning("Unknown command %s, replying empty packet", command.data)
        self.respond(Response(""))

    def handle_question(self, command):
        self.respond(Response("S05"))

    q_splitter = re.compile(r'[,:]')

    def handle_q(self, command):
        try:
            subcmd, args = self.q_splitter.split(str(command.data, 'ascii', 'ignore'), 1)
        except ValueError:
            subcmd = str(command.data, 'ascii')
            args = ""
        subcmd = subcmd
        handler = getattr(self, "handle_" + subcmd, self.handle_unknown)
        handler(command, args)

    handle_Q = handle_q
    handle_v = handle_q

    monitor_splitter = re.compile(r'[ ]*')

    def handle_qRcmd(self, command, args):
        args = str(binascii.a2b_hex(args.encode('ascii')), 'utf-8')
        args = args.split(' ')
        subcmd = args[0]
        if subcmd:
            args = args[1:]
            handler = getattr(self, "monitor_" + subcmd, self.handle_unknown)
            handler(command, args)
        else:
            import inspect
            lines = ["Monitor commands:"]
            for name, func in sorted(inspect.getmembers(self, predicate = inspect.ismethod)):
                if not name.startswith("monitor_"):
                    continue
                lines.append("  %-10s: %s" % (name[8:], func.__doc__ or ""))
            self.respond(HexEncodedResponse("\n".join(lines) + "\n"))

    def handle_QStartNoAckMode(self, command, args):
        self.packet_ack = False
        self.respond(Ok())

    def handle_qSupported(self, command, args):
        args = args.split(";")
        self.respond(Response(";".join(self.features)))

    def handle_qXfer(self, command, args):
        args = args.split(":")
        
        begin, length = map(lambda x:int(x, 16), args[3].split(','))
        end = begin + length

        if args[:3] == ["features", "read", "target.xml"]:
            rsp = self.__target_xml
        elif args[:3] == ["memory-map", "read", ""]:
            rsp = self.__memorymap_xml
        else:
            rsp = b''
            
        s = b'l' if len(rsp) <= end else b'm'
        self.respond(Response(s + rsp[begin:end]))
        
    def handle_qfThreadInfo(self, command, args):
        self.respond(Response(','.join(map(str, self.thread_ids()))))

    def handle_qsThreadInfo(self, command, args):
        self.respond(Response("l"))

    def handle_qC(self, command, args):
        self.respond(Response(str(self.cur_thread_id)))

    def handle_qSymbol(self, command, args):
        value, name = args.split(':', 1)
        name = str(binascii.a2b_hex(name.encode('ascii')), 'utf-8')
        if name:
            if value:
                self.symbol[name] = int(value, 16)
            else:
                self.symbol[name] = None
        if self.symbols_to_resolve:
            name = self.symbols_to_resolve.pop()
            return self.respond(Response('qSymbol:%s' % str(binascii.b2a_hex(name.encode('utf-8')), 'ascii')))
        self.symbols_done()
        self.respond(Ok())

    def symbols_done(self):
        pass

    def handle_H(self, command):
        self.thread_select(int(command.data[2:], 16))
        self.respond(Ok())

    def handle_g(self, command):
        regs = self.reg_get(self.registers)
        ret = b""
        for reg in self.registers:
            if reg in regs:
                ret += binascii.b2a_hex(regs[reg].to_bytes(reg.width // 8,
                                                           byteorder = self.endianness))
            else:
                ret += 'x' * (reg.width // 4)
        self.respond(Response(str(ret, 'ascii')))
        
    def handle_G(self, command):
        value = command.data[1:]
        to_set = {}
        for reg in self.registers:
            if not value:
                break
            v = value[: reg.width // 8]
            value = value[reg.width // 8 :]
            if v.lower() == "x" * len(v):
                continue
            to_set[reg] = int.from_bytes(binascii.a2b_hex(value),
                                         byteorder = self.endianness)
        self.reg_set(to_set)

    def handle_P(self, command):
        # Set register
        # < Pno=value
        # > OK
        ass = command.data.index(b"=")
        no = int(command.data[1 : ass], 16)
        value = command.data[ass + 1 :]
        reg = self.registers[no]
        value = int.from_bytes(binascii.a2b_hex(value),
                               byteorder = self.endianness)
        self.reg_set({reg:value})
        self.respond(Ok())

    def handle_p(self, command):
        # Get register
        # < pno
        # > xxx
        no = int(command.data[1:], 16)
        try:
            reg = self.registers[no]
        except IndexError:
            self.logger.error("Bad register number %d" % no)
            self.respond(Error(-1))
            return
        regmap = self.reg_get([reg])
        value = regmap[reg]
        blob = value.to_bytes(length = reg.width // 8, byteorder = self.endianness)
        self.respond(Response(binascii.b2a_hex(blob)))

    def handle_m(self, command):
        comma = command.data.index(b",")
        begin = int(command.data[1 : comma], 16)
        size = int(command.data[comma + 1 :], 16)
        data = self.memory_read(begin, size)
        
        self.respond(Response(str(binascii.b2a_hex(data), 'ascii')))
        
    def handle_M(self, command):
        # Write memory
        # < Maddr,length:xx...
        # > OK
        # > E nn
        comma = command.data.index(b",")
        colon = command.data.index(b":")
        begin = int(command.data[1 : comma], 16)
        size = int(command.data[comma + 1 : colon], 16)
        blob = command.data[colon + 1 :]
        blob = binascii.a2b_hex(blob)

        self._handle_mem_write(command, begin, size, blob)
        
    def handle_X(self, command):
        # Write memory (binary)
        # < Xaddr,length:xx...
        # > OK
        # > E nn
        comma = command.data.index(b",")
        colon = command.data.index(b":")
        begin = int(command.data[1 : comma], 16)
        size = int(command.data[comma + 1 : colon], 16)
        blob = command.data[colon + 1 :]

        self._handle_mem_write(command, begin, size, blob)

    def _handle_mem_write(self, command, begin, size, blob):
        if not size:
            return self.respond(Ok())

        self.memory_write(begin, blob)
        self.respond(Ok())
        
       
    def handle_c(self, command):
        self.resume()
        self.handle_question(command)

    def handle_s(self, command):
        self.step()
        self.handle_question(command)

    def handle_question(self, command = None):
        if self.run_state == Cpu.State.RUN:
            return
        reason = self.halt_cause
        reason_map = {
            Cpu.HaltCause.EXCEPTION: "T05syscall_entry:;",
            Cpu.HaltCause.INSTRUCTION: "S04",
            Cpu.HaltCause.BREAKPOINT: "T05hwbreak:;",
            Cpu.HaltCause.WATCHPOINT: "T05watch:;",
            Cpu.HaltCause.DEBUGGER: "T05hwbreak:;",
            Cpu.HaltCause.UNKNOWN: "T00",
        }

        self.respond(Response(reason_map[reason]))
        
    def handle_interrupt(self):
        self.halt()
        self.handle_question()

    def monitor_reset(self, command, args):
        """Reset and halt target"""
        self.reset()
        self.respond(Ok())
    
    def handle_R(self, command):
        self.reset()

    def handle_vFlashErase(self, command, args):
        colon = command.data.index(b":")
        comma = command.data.index(b",")
        begin = int(command.data[colon + 1 : comma], 16)
        size = int(command.data[comma + 1 :], 16)
        self.flash_erase(begin, size)
        self.__flash_image = Program()
        self.respond(Ok())

    def handle_vFlashWrite(self, command, args):
        cmd, addr, data = command.data.split(b":", 2)
        address = int(addr, 16)
        self.__flash_image.append(Segment(address, data))
        self.respond(Ok())

    def handle_vFlashDone(self, command, args):
        self.flash(self.__flash_image)
        self.respond(Ok())

    # API to override
        
    def thread_ids(self):
        return [1]

    def thread_select(self, id):
        self.cur_thread_id = id

    def reset(self):
        pass

    def step(self):
        pass

    def resume(self):
        pass

    def halt(self):
        pass

    @property
    def run_state(self):
        return Cpu.State.RUN

    @property
    def halt_cause(self):
        return Cpu.HaltCause.UNKNOWN
    
    @property
    def registers(self):
        return []

    def reg_set(self, registers):
        pass

    def reg_get(self, registers):
        return dict([(r, 0) for r in registers])

    def memory_read(self, addr, size):
        return b'\x00' * size

    def memory_write(self, addr, blob):
        pass

    def flash(self, program):
        self.logger.trace("Loading program to flash")
        program.pprint(self.logger.trace)

    def flash_erase(self, address, size):
        self.logger.trace("Flash erase 0x%08x-0x%08x", address, address + size)
        
    def memory_map_xml(self):
        return b''

