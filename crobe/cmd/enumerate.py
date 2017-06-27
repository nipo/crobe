def main():
    from . import base
    
    class Tool(base.Speed, base.Power, base.IcePick, base.Field):
        pass

    args = Tool("Target enumerator")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Nickname:", args.interface.port.nickname)
    print("Speed:", args.interface.speed)
    
    component_dump(args.interface)
    component_dump(args.field)
    
def component_dump(comp, prefix = ""):
    print(prefix, comp)
    for c in comp.children:
        component_dump(c, prefix + "  ")
    
if __name__ == '__main__':
    main()


