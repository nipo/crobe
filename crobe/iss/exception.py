class IssException(Exception):
    pass

class UndefinedInstruction(IssException):
    pass

class MemoryError(IssException):
    pass

class SoftwareInterrupt(IssException):
    pass
