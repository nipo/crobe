class Range:
    def __init__(self, address, size):
        import traceback

        self.address = address
        self.size = size
        assert size

        self.allocated_on = traceback.extract_stack()

    @property
    def end(self):
        return self.address + self.size
        
    def touches(self, other):
        if self.address > other.address:
            self, other = other, self

        return self.end == other.address

    def merge(self, other):
        if self.address > other.address:
            self, other = other, self

        assert self.end == other.address

        return Range(self.address, other.size + self.size)

    def split(self, size):
        assert size <= self.size

        if size == self.size:
            return self, None
        return Range(self.address, size), \
            Range(self.address + size, self.size - size)

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
        if address >= self.address:
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
        return '<@%#x, %#x>' % (self.address, self.size)

    def __repr__(self):
        return 'Range(%#x, %#x)' % (self.address, self.size)
    
class Allocator:
    def __init__(self, address, size):
        self.__address = address
        self.__size = size
        self.__free = set([Range(address, size)])
        self.__used = set()
        self.assert_complete()

    def allocate(self, size, align = 1):
        size = size or 4
        #print(f"Allocating {size:#x}")
        self.assert_complete()
        target = None
        assert size
        
        for i, maybe in enumerate(self.__free):
            can_split = maybe.split_alloc(size, align)

            if not can_split:
                continue

            left, allocated, right = can_split

            if target:
                t, (left_t, allocated_t, right_t) = target
                if left + right < left_t + right_t:
                    target = maybe, can_split
            else:
                target = maybe, can_split

            if not left and not right:
                break

        #print(f"Target {target}")
            
        if not target:
            #self.dump()
            raise ValueError("No space left", size)

        ret, (left, allocated, right) = target
        assert ret
        #print(f"Ret {ret}")
        
        self.__free.remove(ret)
        if left:
            crumb, ret = ret.split(left)
            #print(f"Split {crumb} {ret}")
            assert crumb
            assert ret
            self.merge_free(crumb)

        if right:
            ret, crumb = ret.split(allocated)
            #print(f"Split {ret} {crumb}")
            assert crumb
            assert ret
            self.merge_free(crumb)

        self.__used.add(ret)

        assert ret.address % align == 0
        self.assert_complete()
        return ret

    def assert_complete(self):
        point = self.__address
        for r in sorted(self.__free | self.__used):
            assert r.address == point, (hex(r.address), hex(point))
            point = r.end
        assert point == self.__address + self.__size
    
    def free(self, r):
        #print("Freeing", r)
        #self.dump()
        self.assert_complete()
        self.__used.remove(r)
        self.merge_free(r)
        #self.dump()
        self.assert_complete()
        #print()
        #print()

    def merge_free(self, r):
        for i in range(2):
            for b in self.__free:
                if b.touches(r):
                    self.__free.remove(b)
                    x = r.merge(b)
                    #print("Merging", r, b, x)
                    r = x
                    break
        self.__free.add(r)
        
    def dump(self):
        print(self)
        print("Free:")
        for r in sorted(self.__free):
            print(r)
            print(r.allocated_on[-6:])
        print("Used:")
        for r in sorted(self.__used):
            print(r)
            print(r.allocated_on[-6:])

    def __str__(self):
        return '<Allocator %s>' % ', '.join([str(b) for b in self.__free])

    def __contains__(self, el):
        return el in self.__used

    def __iter__(self):
        return iter(self.__used)
