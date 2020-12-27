def ctz(value):
    c = 0
    while (value & 1) == 0:
        value >>= 1
        c += 1
    return c

def bit_get(value, bit):
    return (value >> bit) & 1

