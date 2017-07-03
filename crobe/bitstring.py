class BitStringSlice:
    def __init__(self, bs, begin, end):
        self.__bs = bs
        self.__begin = begin
        self.__end = end
        self.__length = end - begin

    def __int__(self):
        begin_byte = self.__begin // 8
        begin_bit = self.__begin & 7
        end_byte = (self.__end + 7) // 8

        blob = self.__bs.data[begin_byte : end_byte]

        return (int.from_bytes(blob, byteorder = 'little') >> begin_bit) & ((1 << (self.__length)) - 1)

    @property
    def data(self):
        return int(self).to_bytes(length = (self.__length + 7)//8, byteorder = 'little')

    def __len__(self):
        return self.__length
    
    def __bool__(self):
        return bool(self.__length)

    def __add__(self, other):
        n = BitString(int(self), self.__length)
        n.append(other)
        return n

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
                return BitString(0, 0)

            return BitStringSlice(self.__bs, self.__begin + b, self.__begin + e)

        if offset < 0:
            offset += self.__length

        offset = self.__begin + offset
        data = self.__bs.data

        return bool(data[offset // 8] & (1 << (offset & 7)))

    def __str__(self):
        if self.__length > 1024:
            return "[%d bits]" % self.__length

        if self.__length:
            return bin(int(self))[2:][::-1].ljust(self.__length, '0')
        return "."
        
    def __repr__(self):
        if self.__length > 1024:
            return "BitString([...], %d)" % (self.__length)
        return "BitString(%r, %d)" % (self.data, self.__length)

class BitString:
    """
    A bitstring.

    A sized binary string.
    """
    
    def __init__(self, *args, **kwargs):
        """
        Creates a new bit string, uses prototype of append().
        """
        self.__bytes = []
        self.__last_byte = 0
        self.__length = 0
        self.__data_cache = None
        if args or kwargs:
            self.append(*args, **kwargs)

    def append(self, data, length = None):
        """
        :param data: May either be a bytes() array, an integer, or another BitString object.
        :param int length: Size (if data is an integer or bytes()).

        If data is bytes, it is parsed little endian, LSB first.
        If length is omitted, it is assumed to be total (i.e. 8 * len(data)).

        If data is an integer, it is used LSB first, providing length
        is mandatory.
        """
        if isinstance(data, (BitString, BitStringSlice)):
            length = len(data)
            if self.__length & 7:
                data = int(data)
            else:
                data = data.data

        if isinstance(data, (bytes, bytearray)):
            if length is None:
                length = len(data) * 8

            if self.__length & 7:
                data = int.from_bytes(data, byteorder = "little")
                data <<= (self.__length & 7)
                data |= self.__last_byte
                length += self.__length & 7
                self.__length &= ~7
                data = data.to_bytes(length = (length + 7) // 8, byteorder = "little")
        elif isinstance(data, int):
            if data < 0:
                data += 1 << length
            data &= (1 << length) - 1

            if self.__length & 7:
                data <<= (self.__length & 7)
                data |= self.__last_byte
                length += self.__length & 7
                self.__length &= ~7
            data = data.to_bytes(length = (length + 7) // 8, byteorder = "little")
            
        self.__length += length
        if self.__length & 7:
            self.__last_byte = data[-1]
            self.__bytes.append(data[:-1])
        else:
            self.__bytes.append(data)
            self.__last_byte = 0

        self.__data_cache = None

    def __iadd__(self, other):
        if not self.__length and isinstance(other, BitString):
            self.__length = other.__length
            self.__bytes = other.__bytes
            self.__last_byte = other.__last_byte
            self.__data_cache = other.__data_cache
            return self
        self.append(other)
        return self

    def __add__(self, other):
        n = BitString(self.data, len(self))
        n.append(other)
        return n

    @property
    def data(self):
        """
        Binary representation of bit string as a blob. LSB first, little-endian.
        """
        if self.__data_cache is None:
            if self.__length & 7:
                self.__data_cache = b''.join(self.__bytes + [bytes([self.__last_byte])])
            else:
                self.__data_cache = b''.join(self.__bytes)

        return self.__data_cache

    def __len__(self):
        """
        Length of bit string, in bits.
        """
        return self.__length

    def __getitem__(self, offset):
        """
        If used to retrieve a sigle bit, it returns a bool.

        If used to retrieve a slice, a BitString is returned.
        Negative indices are supported, stride is not.
        """
        data = self.data

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

            return BitStringSlice(self, b, e)

        if offset < 0:
            offset += self.__length

        return bool(data[offset // 8] & (1 << (offset & 7)))

    def __str__(self):
        """
        String representation, in bit order (LSB first).
        """
        if self.__length > 1024:
            return "[%d bits]" % self.__length

        if self.__length:
            return bin(int(self))[2:][::-1].ljust(self.__length, '0')
        return "."

    def __repr__(self):
        if self.__length > 1024:
            return "BitString([...], %d)" % (self.__length)
        return "BitString(%r, %d)" % (self.data, self.__length)

    def __bool__(self):
        """
        Whether BitString is zero length (regardless of value).
        """
        return bool(self.__length)

    def __int__(self):
        """
        Integer representation of data.
        """
        return int.from_bytes(self.data, byteorder = 'little')

if __name__ == "__main__":
    a = BitString(0x1234, 16)
    print(a)
    b = BitString(0x3456, 15)
    print(b)
    c = a + b
    print(c)
    d = BitString(0xff, 8)
    print(d)
    e = c + d
    print(e)

    print(e[2:10])
    
