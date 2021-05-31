import hvac
from hvac.exceptions import InvalidRequest
from . import FARADAY_VAULT_SERVER, ROLE_ID, SECRET_ID

try:
    ***REMOVED*** = hvac.Client(url=FARADAY_VAULT_SERVER)
    ***REMOVED***.auth.approle.login(role_id=ROLE_ID, secret_id=SECRET_ID)
except InvalidRequest as e:
    print(f"Cannot connect to Vault server: {e}")
    exit(1)


def get_secret(secret_name):
    """ Gets a given secret from Vault

    :param secret_name: Name of the secret stored in Vault
    :type secret_name: str
    :return: Secret's content
    :rtype: str if secrets exists, Exception otherwise
    """
    try:
        if ***REMOVED*** and ***REMOVED***.is_authenticated():
            secret_response = ***REMOVED***.secrets.kv.v2.read_secret_version(
                mount_point='secrets',
                path='gorrabot'
            )
            return secret_response['data']['data'][secret_name]
    except KeyError:
        print("Secret not found")
        exit(1)
