import time
import logging

# CRITICAL = 50
# ERROR = 40
# WARNING = 30
NOTE = 25
# INFO = 20
TRACE = 15
# DEBUG = 10
PROTOCOL = 5
# NOTSET = 0

logging.addLevelName(NOTE, "NOTE")
logging.addLevelName(TRACE, "TRACE")
logging.addLevelName(PROTOCOL, "PROTOCOL")

LEVEL_COLOR = {
    'CRITICAL': '91',
    'ERROR': '31',
    'WARNING': '33',
    'NOTE': '32',
    'INFO': '',
    'TRACE': '94',
    'DEBUG': '34',
    'PROTOCOL': '96',
    'NOTSET': '90',
}

class TimedContext:
    def __init__(self, logger, message):
        self.logger = logger
        self.message = message

    def __enter__(self):
        self.begin = time.time()
        self.logger.trace("Starting to %s...", self.message)

    def __exit__(self, exc_type, exc_value, traceback):
        duration = time.time() - self.begin
        self.logger.trace("Done %s, took %.3f seconds", self.message, duration)

class Progresser:
    def __init__(self, logger, label, count):
        self.logger = logger
        self.label = label
        self.point = 0
        self.count = count

    def step(self, count = 1):
        self.set(self.point + count)

    def set(self, point):
        self.point = point

    def iterate(self, iterable):
        for element in iterable:
            yield element
            self.step()
        
class TqdmProgresser(Progresser):
    def __init__(self, logger, label, count):
        super().__init__(logger, label, count)
        self.progressbar = None

    def set(self, point):
        super().set(point)
        assert self.progressbar is not None
        self.progressbar.update(point - self.last_point)
        self.last_point = point
        
    def __enter__(self):
        from tqdm import tqdm
        assert self.progressbar is None
        self.progressbar = tqdm(total = self.count, desc = self.label)
        self.last_point = 0
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        assert self.progressbar is not None
        self.progressbar.close()
        self.progressbar = None
        
class TextProgresser(Progresser):
    def set(self, point):
        super().set(point)
        self.logger.trace("%s at %d/%d", self.label, self.point, self.count)

    def __enter__(self):
        self.logger.trace("%s starting, %d steps", self.label, self.count)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.logger.trace("%s done", self.label)
        
class CrobeLogger(logging.getLoggerClass()):
    def timed(self, message):
        return TimedContext(self, message)

    def progress(self, label, count):
        if self.isEnabledFor(TRACE):
            return TextProgresser(self, label, count)
        return TqdmProgresser(self, label, count)

    def note(self, msg, *args, **kwargs):
        self.log(NOTE, msg, *args, **kwargs)

    def trace(self, msg, *args, **kwargs):
        self.log(TRACE, msg, *args, **kwargs)

    def protocol(self, msg, *args, **kwargs):
        self.log(PROTOCOL, msg, *args, **kwargs)

logging.setLoggerClass(CrobeLogger)

class DomainFilter(logging.Filter):
    silent = set()

    def __init__(self, off, silent_re = None, only_re = None):
        logging.Filter.__init__(self)
        self.silent = set(off)
        self.silent_re = None
        self.only_re = None
        if only_re is not None:
            self.only_re = re.compile(only_re)
        if silent_re is not None:
            self.silent_re = re.compile(silent_re)

    def filter(self, record):
        if record.name in self.silent:
            return False
        if self.silent_re is not None and self.silent_re.match(record.name):
            return False
        if self.only_re is not None:
            if self.only_re.match(record.name) or record.name == "cli":
                return True
            return False
        return True

class Formatter(logging.Formatter):
    def __init__(self, color = True, timestamp = False):
        line = '\x1b[G\x1b[2K'
        if timestamp:
            line += '{relativeCreatedSec:5.3f} '
        if color:
            line += '\x1b[{color}m'
        line += '{name}: {message}'
        if color:
            line += '\x1b[m'

        super().__init__(fmt = line, style = "{")
        self.timestamp = timestamp
        self.color = color

    def usesTime(self):
        return self.timestamp
        
    def format(self, record):
        record.message = record.getMessage()
        if self.timestamp:
            record.asctime = self.formatTime(record, self.datefmt)
        record.relativeCreatedSec = record.relativeCreated / 1000
        record.color = LEVEL_COLOR[record.levelname]
        s = self.formatMessage(record)
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + record.exc_text
        if record.stack_info:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + self.formatStack(record.stack_info)
        return s
