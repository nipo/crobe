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
            if r.address % align:
                pre = -r.address % align
            else:
                pre = 0
            if r.size >= size + pre and (not target or target.size > r.size):
                target = r

        if not target:
            raise ValueError("No space left")

        if target.address % align:
            pre = -target.address % align
        else:
            pre = 0

        self.__free.remove(target)
        if pre:
            crumb, target = target.split(pre)
            self.__free.add(crumb)
        ret, crumb = target.split(size)
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
