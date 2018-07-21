def main():
    import sys
    import binascii
    from .jed import Jed
    from ..util import endian

    j = Jed(sys.argv[1])
    print("Jedec file for device %s pinout %s" % (j.device_architecture, j.device_pinout))
    print("Package with %d pins" % (j.pin_count))
    print("%d fuse bits" % (len(j.fuses)))
    blob = bytes(j.fuses)
#    blob = endian.bitswap8(blob)
    for off in range(0, len(blob), 16):
        print(str(binascii.b2a_hex(blob[off:off+16][::-1]), 'ascii'))

if __name__ == '__main__':
    main()
