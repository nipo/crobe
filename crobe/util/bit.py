def ctz(value):
    c = 0
    while (value & 1) == 0:
        value >>= 1
        c += 1
    return c
