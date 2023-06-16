from functools import partial
from decorator import decorator
import random
import time
import inspect

def _retry_call(*, call, to_catch, times, delay, logger):
    name = call.func.__name__
    if logger:
        logger.debug("Retrying %s at most %d times", name, times)
    for retry in range(times, -1, -1):
        try:
            r = call()
            if logger:
                logger.debug("%s OK", name)
            return r
        except to_catch as e:
            if not retry:
                raise

            if logger:
                logger.info("Call %d/%d to %s failed with exception %s", 1 + times - retry, times, name, e)
                logger.debug("Retry in %1.2f seconds", delay)

            time.sleep(delay)

def retry(func, *, args = None, kwargs = None, to_catch = Exception, times = 3, delay = 0, logger = None):
    args = args or []
    kwargs = kwargs or {}
    return _retry_call(call = partial(func, *args, **kwargs), to_catch = to_catch, times = times, delay = delay, logger = logger)

def retried(times = 3, *, to_catch = Exception, delay = 0, logger = None):
    from ..model import Component
    @decorator
    def retry_decorator(func, *args, **kwargs):
        logger_inst = None
        if args:
            if (isinstance(args[0], Component) or hasattr(args[0], "logger")):
                logger_inst = args[0].logger
            elif inspect.isfunction(logger):
                logger_inst = logger(args[0])
        return retry(func, args = args, kwargs = kwargs, to_catch = to_catch, times = times, delay = delay, logger = logger_inst)
    return retry_decorator
