import os
import requests

GITLAB_TOKEN = os.environ['GITLAB_TOKEN']
GITLAB_REQUEST_TOKEN = os.environ['GITLAB_CHECK_TOKEN']
GITLAB_SELF_USERNAME = os.environ['GITLAB_BOT_USERNAME']

GITLAB_API_PREFIX = 'https://gitlab.com/api/v4'

gitlab_session = requests.Session()
gitlab_session.headers['Private-Token'] = GITLAB_TOKEN


class GitlabLabels:
    NO_ME_APURES = 'no-me-apures'
    NO_CHANGELOG = 'no-changelog'
    SACATE_LA_GORRA = 'sacate-la-gorra'
    MULTIPLE_MR = 'multiple-merge-requests'
    TEST = 'Test'
    ACCEPTED = 'Accepted'
