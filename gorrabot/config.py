import yaml
from api.vault import get_secret


def read_config() -> dict:
    with open("config.yaml", 'r') as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(exc)
            exit(1)


config = read_config()
