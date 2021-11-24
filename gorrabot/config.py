import os
import yaml
import re
from functools import lru_cache

from gorrabot.api.vault import SECRETS, GORRABOT_CONFIG_FILE, get_secret


DEBUG_MODE = os.environ.get('GORRABOT_DEBUG')
NOTIFY_DEFAULT_CHANNEL = os.environ.get('NOTIFY_DEFAULT_CHANNEL')
NOTIFY_DEBUG_CHANNEL = os.environ.get('NOTIFY_DEBUG_CHANNEL')


def load_yaml(data):  # TODO I DO NOT LIKE THIS HERE
    try:
        return yaml.safe_load(data)
    except yaml.YAMLError as exc:
        print(exc)
        exit(1)


@lru_cache(maxsize=None)
def config() -> dict:
    secret = get_secret(SECRETS['config']) if 'config' in SECRETS else GORRABOT_CONFIG_FILE['path']
    if not secret:
        print("Invalid secret: Be sure you've set either CONFIG_SECRET_NAME or GORRABOT_CONFIG_FILE")
        exit(1)

    if re.match(GORRABOT_CONFIG_FILE['path_regex'], secret):  # must be an absolute path
        if not secret.endswith('.yaml'):
            print("Invalid GORRABOT_CONFIG_FILE: It must be a .yaml file")
            exit(1)

        try:
            with open(secret, 'r') as stream:
                return load_yaml(stream)
        except FileNotFoundError:
            print("File not found")
            exit(1)

    return load_yaml(secret)


config()
