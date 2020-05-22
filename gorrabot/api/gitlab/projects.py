from gorrabot.api.gitlab import GITLAB_API_PREFIX, gitlab_session


def get_project_name(project_id: int):
    res = gitlab_session.get(GITLAB_API_PREFIX + f'/projects/{project_id}')
    res.raise_for_status()
    return res.json()['name']
