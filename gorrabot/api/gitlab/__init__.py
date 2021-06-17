import os
import requests

from gorrabot.config import config

GITLAB_TOKEN = os.environ['GITLAB_TOKEN']
GITLAB_REQUEST_TOKEN = os.environ['GITLAB_CHECK_TOKEN']
GITLAB_SELF_USERNAME = os.environ['GITLAB_BOT_USERNAME']

GITLAB_API_PREFIX = 'https://gitlab.com/api/v4'

gitlab_session = requests.Session()
gitlab_session.headers['Private-Token'] = GITLAB_TOKEN


class GitlabLabels:
    DONT_RUSH_ME = config['gitlab']['labels'].get('DONT_RUSH_ME', 'Do not rush me')
    NO_CHANGELOG = config['gitlab']['labels'].get('NO_CHANGELOG', 'No changelog')
    DONT_TRACK = config['gitlab']['labels'].get('DONT_TRACK', 'Do not track')
    MULTIPLE_MR = config['gitlab']['labels'].get('MULTIPLE_MR', 'Multiple MR')
    TEST = config['gitlab']['labels'].get('TEST', 'Test')
    ACCEPTED = config['gitlab']['labels'].get('ACCEPTED', 'Accepted')
