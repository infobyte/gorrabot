import threading
from queue import Queue
buffer = Queue()


class Worker(threading.Thread):
    def __init__(self, buffer, handler):
        super().__init__(daemon=True)
        self.buffer = buffer
        self.handler = handler
        self.start()

    def run(self):
        while True:
            data = self.buffer.get()
            try:
                self.handler(data)
            except Exception:
                pass
            self.buffer.task_done()
