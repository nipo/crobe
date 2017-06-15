def main():
    from . import base
    
    class Tool(base.Interface):
        pass

    args = Tool("XVCD Server")

    print("Adapter:", args.interface.port.firmware_info)
    print("Serial:", args.interface.port.serial_number)
    print("Speed:", args.interface.speed)
    
    args.interface.start()
    
if __name__ == '__main__':
    main()


