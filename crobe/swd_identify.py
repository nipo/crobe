from .adapter.jlink import Enumerator
from .arm.dap import Dap
from .model import Bus
import time
import binascii
import hexdump

def main():
    swd = Enumerator().get(index = 0).open("swd")
    print "Adapter:", swd.adapter.firmware_info
    print "Serial:", swd.adapter.serial_number
    swd.speed = 1000e3
    print "Speed:", swd.speed

    swd.adapter.reset = True
    time.sleep(.005)
    swd.adapter.reset = False
    time.sleep(.005)
    
    dap = Dap(swd)
    root = dap.component()

    component_dump(root)

def component_dump(comp, prefix = ""):
    print prefix, comp
    for c in comp.children:
        component_dump(c, prefix + "  ")

if __name__ == '__main__':
    main()


