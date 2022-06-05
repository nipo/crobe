
def ascii_escaped(d):
    return ''.join((chr(c) if 0x20 <= c <= 0x7f else '.') for c in d)

def line_dump(address, data, printer, line_bytes = 16):
    blank_pre = address % line_bytes
    blank_post = -(address + len(data)) % line_bytes

    printer(f"{address:#010x}: {' ' * blank_pre * 3}{''.join('%02x '%x for x in data)}{' ' * blank_post * 3}| {' ' * blank_pre}{ascii_escaped(data)}")

def hexdump(address, data, printer, line_bytes = 16):
    addr_min = address - address % line_bytes
    end = address + len(data)
    addr_max = end + (-end) % line_bytes

    for addr in range(addr_min, addr_max, line_bytes):
        line_start = max(addr, address)
        line_end = addr + line_bytes

        chunk = data[line_start - address : line_end - address]
        line_dump(line_start, chunk, line_bytes = line_bytes, printer = printer)
