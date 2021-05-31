import yaml
from api.vault import SECRET_NAME, get_secret

secret = get_secret(SECRET_NAME)


def read_config() -> dict:
    try:
        return yaml.safe_load(secret)
    except yaml.YAMLError as exc:
        print(exc)
        exit(1)


config = read_config()
