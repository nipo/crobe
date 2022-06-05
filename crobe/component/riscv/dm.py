from ...db import Db, NoMatch
from ...model import PortComponent

class AccessFailure(Exception):
    pass

class Write:
    def __init__(self, address, data):
        self.address = address
        self.data = data
        self.success = None

    def __repr__(self):
        if self.success:
            status = "OK"
        elif self.success is None:
            status = "?"
        else:
            status = "Fail"
        if isinstance(self.data, int):
            return f"<Wr {self.address:#010x}: {self.data:#010x} {status}>"
        else:
            return f"<Wr {self.address:#010x}: {self.data} {status}>"

class Read:
    def __init__(self, address):
        self.address = address
        self.data = None
        self.success = None

    def __repr__(self):
        if self.success:
            status = "OK"
        elif self.success is None:
            status = "?"
        else:
            status = "Fail"
        return f"<Rd {self.address:#010x}: {hex(self.data) if self.data is not None else '-'} {status}>"

class DebugModule(PortComponent):
    version_db = Db("Version")

    """
    Debug Modules are not necessarily at the start of the address
    space. All registers are offset from the base.

    execute() is responsible for offsetting the register address correctly.
    """

    version = "?"
    REG_DMSTATUS     = 0x11 # Debug Module Status

    def __init__(self, port, *, idcode, base, index):
        super().__init__(port, f"DM#{index}")
        self.base = base
        self.idcode = idcode
        self.index = index

    def __str__(self):
        return "%s (%s, @%#x)" % (
            self.name, self.version, self.base)
        
    def execute(self, operations):
        self.port.dmi_execute(operations)

    def cmd_read(self, address):
        return Read(address)

    def cmd_write(self, address, data):
        return Write(address, data)

    def next_base_get(self):
        return 0
    
    def read(self, address):
        r = Read(address)
        self.execute([r])
        if r.success is not True:
            self.logger.warning("Access failed: %s", r.success)
            raise AccessFailure()
        return r.data

    def write(self, address, data):
        w = Read(address, data)
        self.execute([w])
        if r.success is not True:
            self.logger.warning("Access failed: %s", r.success)
            raise AccessFailure()

    def cast(self):
        try:
            status = self.read(self.REG_DMSTATUS)
        except AccessFailure:
            self.logger.warning("Could not retrieve status register")
            return self
        try:
            return self.version_db.call(status & 0xf,
                                     port = self.port,
                                     idcode = self.idcode,
                                     base = self.base,
                                     index = self.index)
        except NoMatch:
            self.logger.warning("No DM specialization for version %#x", status & 0xf)
            return self

@DebugModule.version_db.register(1)
class DebugModule011(DebugModule):
    version = 0.11
        
@DebugModule.version_db.register(2)
class DebugModule013(DebugModule):
    version = 0.13
    def __init__(self, port, idcode, base, index):
        super().__init__(port = port,
                         idcode = idcode,
                         base = base,
                         index = index)

    def start(self):
        status = self.cmd_read(self.REG_DMSTATUS)
        hartinfo = self.cmd_read(self.REG_HARTINFO)
        sbcs = self.cmd_read(self.REG_SBCS)
        dmcontrol_before = self.cmd_read(self.REG_DMCONTROL)
        enable = self.cmd_write(self.REG_DMCONTROL, 1)
        dmcontrol = self.cmd_read(self.REG_DMCONTROL)

        self.execute([status, hartinfo, sbcs, dmcontrol_before, enable, dmcontrol])

        status = status.data
        hartinfo = hartinfo.data
        sbcs = sbcs.data

        self.logger.info("Ctrl before: %#010x", dmcontrol_before.data)
        self.logger.info("Status: %#010x", status)
        self.logger.info("HartInfo: %#010x", hartinfo)
        self.logger.info("SBCS: %#010x", sbcs)

        self.logger.trace("Enabling DM Active...")
        self.logger.info("Ctrl: %#010x", dmcontrol.data)

        self.bus = None
        if sbcs & 0xfff:
            from .system_bus import SystemBusAccess
            self.bus = SystemBusAccess(self)
            self.child_add(self.bus)

    def next_base_get(self):
        return self.read(self.REG_NEXTDM)

    REG_DATA         = staticmethod(lambda x: 0x04 + x) # Abstract Data n [0-11]
    REG_DMCONTROL    = 0x10 # Debug Module Control
    REG_HARTINFO     = 0x12 # Hart Info
    REG_HAWINDOWSEL  = 0x14 # Hart Array Window Select
    REG_HAWINDOW     = 0x15 # Hart Array Window
    REG_ABSTRACTCS   = 0x16 # Abstract Control and Status
    REG_COMMAND      = 0x17 # Abstract Command
    REG_ABSTRACTAUTO = 0x18 # Abstract Command Autoexec
    REG_CONFSTRPTR   = staticmethod(lambda x: 0x19 + x) # Configuration Structure Pointer [0-3]
    REG_NEXTDM       = 0x1d # Next Debug Module
    REG_PROGBUF      = staticmethod(lambda x: 0x20 + x) # Program Buffer n [0-15]
    REG_AUTHDATA     = 0x30 # Authentication Data
    REG_SBCS         = 0x38 # System Bus Access Control and Status
    REG_SBADDRESS    = staticmethod(lambda x: 0x37 if x == 3 else (0x39 + x)) # System Bus Address [0-3]
    REG_SBDATA       = staticmethod(lambda x: 0x3c + x) # System Bus Data
    REG_HALTSUM      = staticmethod(lambda x: [0x40, 0x13, 0x34, 0x35][x]) # Halt Summary [0-3]

@DebugModule.version_db.register(3)
class DebugModule10(DebugModule):
    version = 1.0

    def __init__(self, port, idcode, base, index):
        super().__init__(port = port,
                         idcode = idcode,
                         base = base,
                         index = index)

    def start(self):
        status = self.read(self.REG_DMSTATUS)
        self.logger.info("Status: %#010x", status)
        self.logger.info("HartInfo: %#010x", self.read(self.REG_HARTINFO))

    def next_base_get(self):
        return self.read(self.REG_NEXTDM)

    REG_DATA         = staticmethod(lambda x: 0x04 + x) # Abstract Data n [0-11]
    REG_DMCONTROL    = 0x10 # Debug Module Control
    REG_HARTINFO     = 0x12 # Hart Info
    REG_HAWINDOWSEL  = 0x14 # Hart Array Window Select
    REG_HAWINDOW     = 0x15 # Hart Array Window
    REG_ABSTRACTCS   = 0x16 # Abstract Control and Status
    REG_COMMAND      = 0x17 # Abstract Command
    REG_ABSTRACTAUTO = 0x18 # Abstract Command Autoexec
    REG_CONFSTRPTR   = staticmethod(lambda x: 0x19 + x) # Configuration Structure Pointer [0-3]
    REG_NEXTDM       = 0x1d # Next Debug Module
#    REG_CUSTOM       = 0x1f # Custom Features
    REG_PROGBUF      = staticmethod(lambda x: 0x20 + x) # Program Buffer n [0-15]
    REG_AUTHDATA     = 0x30 # Authentication Data
    REG_DMCS2        = 0x32 # Debug Module Control and Status 2
    REG_SBCS         = 0x38 # System Bus Access Control and Status
    REG_SBADDRESS    = staticmethod(lambda x: 0x37 if x == 3 else (0x39 + x)) # System Bus Address [0-3]
    REG_SBDATA       = staticmethod(lambda x: 0x3c + x) # System Bus Data
    REG_HALTSUM      = staticmethod(lambda x: [0x40, 0x13, 0x34, 0x35][x]) # Halt Summary [0-3]
    REG_CUSTOM       = staticmethod(lambda x: 0x70 + x) # [0-15]

@DebugModule.version_db.register(0xf)
class DebugModuleNonStd(DebugModule):
    version = "non-standard"
