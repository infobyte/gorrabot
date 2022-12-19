from gorrabot import server
from gorrabot.worker_factory import Worker, buffer
from gorrabot.config import config

from gorrabot.timer import GorrabotTimer
from gorrabot.event_handling import handle_event

GorrabotTimer(config.cache_clear, 1800)  # execute every 30 minutes
Worker(buffer=buffer, handler=handle_event)
app = server.app


if __name__ == '__main__':
    server.main()
