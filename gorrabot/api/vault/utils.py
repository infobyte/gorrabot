import hvac
from hvac.exceptions import InvalidRequest
from . import FARADAY_VAULT_SERVER, ROLE_ID, SECRET_ID

try:
    ***REMOVED*** = hvac.Client(url=FARADAY_VAULT_SERVER)
    ***REMOVED***.auth.approle.login(role_id=ROLE_ID, secret_id=SECRET_ID)
except InvalidRequest as e:
    print(f"Cannot connect to Vault server: {e}")
    exit(1)