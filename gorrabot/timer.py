from threading import Timer


class GorrabotTimer:
    """Call a function every specified number of seconds:

            gt = GorrabotTimer(f, 1800)
            gt.start()
            gt.stop()     # stop the timer's action

    """

    def __init__(self, function, interval):
        self._timer = None
        self.function = function
        self.interval = interval
        self.is_running = False
        self.start()

    def _run(self):
        self.is_running = False
        self.start()
        self.function()

    def start(self):
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
        self._timer.cancel()
        self.is_running = False