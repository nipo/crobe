from .adapter.jlink import Enumerator
from .adapter.jtag import *

def main():
    jtag = Enumerator().get(index = 0).open("jtag")
    print("Adapter:", jtag.adapter.firmware_info)
    print("Serial:", jtag.adapter.serial_number)
    jtag.speed = 1000e3
    print("Speed:", jtag.speed)
    
    chain = jtag.chain()

    component_dump(chain)

def component_dump(comp, prefix = ""):
    print(prefix, comp)
    for c in comp.children:
        component_dump(c, prefix + "  ")
    
if __name__ == '__main__':
    main()


