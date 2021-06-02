import os

# Vault server constants
FARADAY_VAULT_SERVER = "https://tluav-lb.***REMOVED***.com/"
ROLE_ID = os.environ.get('ROLE_ID')
SECRET_ID = os.environ.get('SECRET_ID')
SECRET_NAME = os.environ.get('SECRET_NAME')
GORRABOT_CONFIG_FILE = {
    'path': os.environ.get('GORRABOT_CONFIG_FILE'),
    'path_regex': '^(/[^/ ]*)+/?$'
}

from .utils import get_secret
