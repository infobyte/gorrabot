from urllib.parse import quote
from functools import lru_cache

from gorrabot.api.gitlab import gitlab_session, GITLAB_API_PREFIX


@lru_cache(maxsize=None)
def get_branch(project_id: int, branch_name: str):
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/repository/branches/{quote(branch_name, safe="")}'
    res = gitlab_session.get(url)
    if res.status_code == 404:
        return
    res.raise_for_status()
    return res.json()
