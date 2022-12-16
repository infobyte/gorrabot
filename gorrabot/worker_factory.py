import threading
from queue import Queue
buffer = Queue()


class Worker(threading.Thread):
    def __init__(self, buffer, handler):
        super().__init__(daemon=True)
        self.buffer = buffer
        self.handler = handler

    def run(self):
        while True:
            self.json = self.buffer.get()
            try:
                self.handler(self.json)
            except Exception:
                pass
            self.buffer.task_done()
