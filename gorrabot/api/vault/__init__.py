import os

# Vault server constants
FARADAY_VAULT_SERVER = "https://tluav-lb.***REMOVED***.com/"
ROLE_ID = os.environ['ROLE_ID']
SECRET_ID = os.environ['SECRET_ID']
SECRET_NAME = os.environ['SECRET_NAME']

from .utils import get_secret
