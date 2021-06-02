import yaml
import re
from gorrabot.api.vault import SECRET_NAME, GORRABOT_CONFIG_FILE, get_secret


def load_yaml(data):
    try:
        return yaml.safe_load(data)
    except yaml.YAMLError as exc:
        print(exc)
        exit(1)


def read_config(secret) -> dict:
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


secret = get_secret(SECRET_NAME) if SECRET_NAME else GORRABOT_CONFIG_FILE['path']
config = read_config(secret)
