import time

class TimedLogger:
    def __init__(self, logger, message):
        self.logger = logger
        self.message = message

    def __enter__(self):
        self.begin = time.time()
        self.logger.info("Starting to %s...", self.message)

    def __exit__(self, exc_type, exc_value, traceback):
        duration = time.time() - self.begin
        self.logger.info("Done %s, took %.3f seconds", self.message, duration)
