from .adapter.jlink import Enumerator
from .arm.dap import Dap
from .model import Bus
import time
import binascii
import logging

def main():
    FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=FORMAT, level = 40)

    swd = Enumerator().get(index = 0).open("swd")
    print("Adapter:", swd.port.firmware_info)
    print("Serial:", swd.port.serial_number)
    swd.speed = 1000e3
    print("Speed:", swd.speed)

    swd.discover()
    
    component_dump(swd)

def component_dump(comp, prefix = ""):
    print(prefix, comp)
    for c in comp.children:
        component_dump(c, prefix + "  ")

if __name__ == '__main__':
    main()


