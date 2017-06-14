def main():
    from .base import Command
    
    class Tool(Command):
        pass

    args = Tool("Node NFC Tag reader")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Speed:", args.interface.speed)
    
    args.interface.start()

    component_dump(args.interface)

def component_dump(comp, prefix = ""):
    print(prefix, comp)
    for c in comp.children:
        component_dump(c, prefix + "  ")
    
if __name__ == '__main__':
    main()


