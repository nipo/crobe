class BitString:
    def __init__(self, *args, **kwargs):
        self.__data = 0
        self.__length = 0
        if args or kwargs:
            self.append(*args, **kwargs)

    def append(self, data, length = None):
        if isinstance(data, bytes):
            if length is None:
                length = len(data) * 8
            data = int.from_bytes(data, byteorder = "little")
        elif data < 0:
            data += 1 << length

        if length % 8:
            data = data & ((1 << length) - 1)
        self.__data |= data << self.__length
        self.__length += length

    def __iadd__(self, other):
        self.append(other.__data, other.__length)
        return self

    def __add__(self, other):
        n = self.__class__(self.__data, self.__length)
        n.append(other.__data, other.__length)
        return n

    @property
    def data(self):
        return self.__data.to_bytes(length = (self.__length + 7) // 8, byteorder = "little")

    def __len__(self):
        return self.__length

    def __getitem__(self, offset):
        if isinstance(offset, slice):
            b, e = offset.start, offset.stop
            if b is None:
                b = 0
            elif b < 0:
                b += self.__length

            if e is None:
                e = self.__length
            elif e < 0:
                e += self.__length

            b = max(0, min(b, self.__length))
            e = max(0, min(e, self.__length))

            if e <= b:
                return self.__class__(0, 0)

            return self.__class__((self.__data >> b) & ((1 << (e - b)) - 1), e - b)

        if offset < 0:
            offset += self.__length

        return bool((self.__data >> offset) & 1)

    def __str__(self):
        if self.__length > 1024:
            return "[%d bits]" % self.__length
        if self.__length:
            return bin(self.__data)[2:][::-1].ljust(self.__length, '0')
        return "."

    def __repr__(self):
        if self.__length > 1024:
            return "BitString([...], %d)" % (self.__length)
        return "BitString(0x%x, %d)" % (self.__data, self.__length)

    def __bool__(self):
        return bool(self.__length)

    def __int__(self):
        return self.__data
