import yaml
from gorrabot.api.vault import SECRET_NAME, GORRABOT_CONFIG_FILE, get_secret


secret = get_secret(SECRET_NAME) if SECRET_NAME else GORRABOT_CONFIG_FILE


def read_config() -> dict:
    try:
        return yaml.safe_load(secret)
    except yaml.YAMLError as exc:
        print(exc)
        exit(1)


config = read_config()
