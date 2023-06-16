import select
import threading
import os
import time
from .. import model

class FileMonitor(model.Component):
    def __init__(self, path, settle_delay = 1):
        super().__init__(path)
        self.path = path
        self.settle_delay = settle_delay
        self.last_mtime = None
        self.running = False

    def path_mtime_get(self):
        try:
            st = os.stat(self.path)
        except Exception:
            return None
        return st.st_mtime

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            now = time.time()
            mtime = self.path_mtime_get()
            last_mtime = self.last_mtime

            if mtime:
                last_change_duration = now - mtime
                if last_change_duration < self.settle_delay:
                    time.sleep(self.settle_delay - last_change_duration)
                    continue

            self.last_mtime = mtime

            if last_mtime == mtime:
                time.sleep(self.settle_delay)
                continue

            self.logger.debug(f"%s -> %s", last_mtime, mtime)

            if mtime is None and last_mtime is not None:
                self.logger.info(f"Disappeared")
                self.on_disappear()
                continue

            if last_mtime is None and mtime is not None:
                self.logger.info("Appeared")
                self.on_appear()
                continue

            if last_mtime and mtime:
                self.logger.info("Updated")
                self.on_update()
                continue

    def on_disappear(self):
        ...

    def on_change(self):
        ...

    def on_appear(self):
        ...
        
class FileMonitorThread(threading.Thread, FileMonitor):
    def __init__(self, path, settle_delay = 1):
        super().__init__()
        FileMonitor.__init__(self, path, settle_delay)
