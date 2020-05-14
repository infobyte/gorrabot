from requests import Session
from urllib.parse import quote

from constants import GITLAB_API_PREFIX


def get_branch(session: Session, project_id: int, branch_name: str):
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/repository/branches/{quote(branch_name, safe="")}'
    res = session.get(url)
    if res.status_code == 404:
        return
    res.raise_for_status()
    return res.json()
