import hvac
from hvac.exceptions import InvalidRequest
from . import VAULT_SERVER, ROLE_ID, SECRET_ID

ERROR_MESSAGE = "VaultError: {}"

try:
    client = hvac.Client(url=VAULT_SERVER)
    client.auth.approle.login(role_id=ROLE_ID, secret_id=SECRET_ID)
except InvalidRequest as e:
    message = f"Cannot connect to Vault server, {e}"
    print(ERROR_MESSAGE.format(message))
    exit(1)


def get_secret(secret_name):
    """ Gets a given secret from Vault

    :param secret_name: Name of the secret stored in Vault
    :type secret_name: str
    :return: Secret's content
    :rtype: str if secrets exists, Exception otherwise
    """
    try:
        if client and client.is_authenticated():
            secret_response = client.secrets.kv.v2.read_secret_version(
                mount_point='secrets',
                path='gorrabot'
            )
            return secret_response['data']['data'][secret_name]
    except KeyError as e:
        message = f"Secret {e} could not be found"
        print(ERROR_MESSAGE.format(message))
        exit(1)
