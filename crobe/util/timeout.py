import time

class TimeoutError(Exception):
    pass

def retry_for(delay):
    start = time.time()
    deadline = start + delay

    yield None
    
    while time.time() < deadline:
        yield None

    raise TimeoutError(f"Timeout after retry for {delay} secs")
