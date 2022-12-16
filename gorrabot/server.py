import os
import logging
import sys

from flask import Flask, request, abort, make_response

from gorrabot.api.gitlab import (
    GITLAB_REQUEST_TOKEN,
    GITLAB_SELF_USERNAME,
)
from gorrabot.worker_factory import Worker, buffer
from gorrabot.api.slack.messages import send_debug_message
from gorrabot.api.slack import SLACK_REQUEST_TOKEN
from gorrabot.slack_commands import handle_summary
from gorrabot.config import DEBUG_MODE, config
from gorrabot.timer import GorrabotTimer
from gorrabot.event_handling import handle_event


app = Flask(__name__)

# Logging set to stdout
root = logging.getLogger()
root.setLevel(logging.DEBUG if 'DEBUG' in os.environ else logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG if 'DEBUG' in os.environ else logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)
logger = logging.getLogger(__name__)


@app.route('/clear-cache')
def clear_vault_cache():
    if not DEBUG_MODE and request.headers.get('X-Gitlab-Token') != GITLAB_REQUEST_TOKEN:
        abort(403)
    logger.info("Clearing Vault cache...")
    config.cache_clear()
    return "OK"


@app.route('/status')
def status():
    return "OK"


@app.route('/slack-commands', methods=['POST'])
def summary():
    content = request.form
    command = content.get('command')
    logger.info(f"Handling Slack command {command}")
    if not DEBUG_MODE and content.get('token') != SLACK_REQUEST_TOKEN:
        logger.info(f"Command {command} Not allow")
        abort(403)
    if command == '/summary':
        response = handle_summary(content)
    elif command == '/branch':
        response = handle_summary(content)
    else:
        logger.info("Command not register")
        abort(404)
    return response


@app.route('/webhook', methods=['POST'])
def homepage():
    if not DEBUG_MODE and request.headers.get('X-Gitlab-Token') != GITLAB_REQUEST_TOKEN:
        abort(403)
    event_json = request.get_json()
    if event_json is None:
        abort(400)
    logger.info("Event received")
    try:
        if event_json['user']['username'] == GITLAB_SELF_USERNAME:
            # To prevent infinite loops and race conditions, ignore events related
            # to actions that this bot did
            message = 'Ignoring webhook from myself'
            logger.info(message)
            send_debug_message(message)
            abort(make_response({"message": message}, 400))
    except KeyError as e:
        pass
        #message = f"{e} parameter expected but not found"
        #logger.info(message)
        #abort(make_response({"message": message}, 400))
    buffer.put(event_json)
    return 'OK'


def main():
    GorrabotTimer(config.cache_clear, 1800)  # execute every 30 minutes
    consumer = Worker(buffer=buffer, handler=handle_event)
    consumer.start()
    app.run()


if __name__ == '__main__':
    main()
