import os

# Vault server constants
VAULT_SERVER = os.environ.get('VAULT_SERVER')
ROLE_ID = os.environ.get('ROLE_ID')
SECRET_ID = os.environ.get('SECRET_ID')
CONFIG_SECRET_NAME = os.environ.get('CONFIG_SECRET_NAME', "")
SECRETS = {secret: secret for secret in CONFIG_SECRET_NAME.split(',') if CONFIG_SECRET_NAME}
GORRABOT_CONFIG_FILE = {
    'path': os.environ.get('GORRABOT_CONFIG_FILE'),
    'path_regex': '^(/[^/ ]*)+/?$'
}

from .utils import get_secret
