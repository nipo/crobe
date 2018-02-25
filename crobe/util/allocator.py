class Range:
    def __init__(self, address, size):
        self.address = address
        self.size = size
        assert size

    @property
    def end(self):
        return self.address + self.size
        
    def touches(self, other):
        if self.address > other.address:
            self, other = other, self

        return self.address + self.size == other.address

    def merge(self, other):
        if self.address > other.address:
            self, other = other, self

        assert self.address + self.size == other.address

        return Range(self.address, other.size + self.size)

    def split(self, size):
        assert size <= self.size

        if size == self.size:
            return self, None
        return Range(self.address, size), Range(self.address + size, self.size - size)

    def split_alloc(self, size, align):
        if self.size < size:
            return

        # try at left side
        if self.address % align:
            address = (self.address | (align - 1)) + 1
        else:
            address = self.address
        if address + size <= self.end:
            left = address - self.address, size, self.end - size - address
        else:
            left = None

        # try at right side
        address = (self.end - size) & ~(align - 1)
        if address + size <= self.end:
            right = address - self.address, size, self.end - size - address
        else:
            right = None

        return right or left
        
    def __hash__(self):
        return hash(self.address) ^ hash(self.size)

    def __eq__(self, other):
        return self.address == other.address and self.size == other.size

    def __lt__(self, other):
        return self.address < other.address

    def __lte__(self, other):
        return self.address <= other.address

    def __str__(self):
        return '<@0x%x, %d>' % (self.address, self.size)

    def __repr__(self):
        return 'Range(0x%x, %d)' % (self.address, self.size)
    
class Allocator:
    def __init__(self, address, size):
        self.__address = address
        self.__size = size
        self.__free = set([Range(address, size)])
        self.__used = set()

    def allocate(self, size, align = 1):
        target = None

        for i, r in enumerate(self.__free):
            can_split = r.split_alloc(size, align)

            if not can_split:
                continue

            left, allocated, right = can_split

            if not left and not right:
                break

            if not target:
                target = r, can_split
                continue

            t, (left_t, allocated_t, right_t) = target
            if left + right < left_t + right_t:
                target = r, can_split

        if not target:
            for r in sorted(self.__used):
                print(r)

            raise ValueError("No space left", size)

        t, (left, allocated, right) = target
        self.__free.remove(t)
        if left:
            crumb, t = t.split(left)
            self.__free.add(crumb)
        ret, crumb = t.split(allocated)
        if crumb:
            self.__free.add(crumb)
        self.__used.add(ret)

        assert ret.address % align == 0
        
        return ret

    def free(self, r):
        self.__used.remove(r)
        for i in range(2):
            for b in self.__free:
                if b.touches(r):
                    self.__free.remove(b)
                    r = r.merge(b)
                    break
        self.__free.add(r)
        
    def __str__(self):
        return '<Allocator %s>' % ', '.join([str(b) for b in self.__free])

    def __contains__(self, el):
        return el in self.__used

    def __iter__(self):
        return iter(self.__used)
