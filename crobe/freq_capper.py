from .util.pretty import metric, sci_parse

class FreqCapper:
    def __init__(self, default_freq = None):
        self.__constraints = {"default" : default_freq}
        self.__freq = object()
        self.__freq_set(default_freq, "default")

    @property
    def freq(self):
        return self.__freq
        
    def freq_cap_min(self, collection):
        for c in collection:
            self.freq_cap(c, c.max_freq)

    def freq_cap(self, key, freq = None):
        if freq is None:
            self.__constraints.pop(key, None)
        else:
            self.__constraints[key] = freq
        caps = [(f, k) for (k, f) in self.__constraints.items() if f]
        caps.sort(key = lambda x:x[0])
        if caps:
            self.__freq_set(caps[0][0], caps[0][1])
        else:
            self.__freq_set()
        return self.__freq

    def __freq_set(self, freq = None, reason = ""):
        if freq == self.__freq:
            return

        self.logger.info("Frequency now capped to %s because of %s",
                         metric(freq, "Hz"), reason)

        freq = self.freq_update(freq)
        if freq is None:
            raise RuntimeError("%s did not return actual freq" % self.freq_update)
        self.__freq = freq

        self.logger.info("  -> got %s", metric(self.freq, "Hz"))

    def freq_update(self, freq):
        return freq
