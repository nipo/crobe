import re

class Register:
    """
    A register definition used at class declaration level to declare
    registers in an ISA.
    """
    def __init__(self, bit_size, *aliases, read_only = False, init = 0, omit = None):
        self.bit_size = bit_size
        self.aliases = aliases
        self.mask = (1 << self.bit_size) - 1
        self.read_only = read_only
        self.init = init
        self.omit = omit if omit is not None else read_only
        
    def contribute(self, target_isa, name):
        def getter(s):
            return s.registers[name]

        def setter(s, v):
            s.registers[name] = v

        doc = f"Register {name}, {self.bit_size} bits"
        if self.aliases:
            doc += f"\nAlso known as {', '.join(self.aliases)}"
        if self.read_only:
            doc += f"\nRead-only"

        prop = property(
            fget = getter,
            fset = setter if not self.read_only else None,
            doc = doc,
            )

        setattr(target_isa, name, prop)
        for a in self.aliases:
            setattr(target_isa, a, prop)

class RegisterSet:
    """
    Registerset live object used to hold all register in a ISA live object.
    """

    splitter = re.compile(r"([0-9]+)")
    
    @classmethod
    def sort_key(cls, reg_name):
        tokens = cls.splitter.split(reg_name)
        for i in range(1, len(tokens), 2):
            tokens[i] = int(tokens[i])
        return tuple(tokens)

    def __init__(self, register_infos):
        self.__infos = {}
        self.__infos.update(register_infos)
        self.__primaries = list(self.__infos.items())
        self.__primaries.sort(key = lambda c:self.sort_key(c[0]))
        self.__canonical = {}
        self.__values = {}

        for name, i in self.__infos.items():
            self.__values[name] = i.init
            for a in i.aliases:
                self.__canonical[a] = name
            self.__canonical[name] = name

    def __getitem__(self, name):
        canon = self.__canonical[name]
        return self.__values[canon]

    def __setitem__(self, name, value):
        canon = self.__canonical[name]
        info = self.__infos[canon]
        if info.read_only:
            return
        self.__values[canon] = info.mask & value

    def dump(self):
        for i, (name, info) in enumerate(self.__primaries):
            if info.omit:
                continue
            v = self.__values[name]
            v_p = ("%%#0%dx" % ((info.bit_size + 3) // 4)) % v
            print(f"{name}: {vp}", end = "\n" if i & 3 == 3 else "  ")
        print()
