from requests import Session

from constants import GITLAB_API_PREFIX


def get_commit_jobs(session: Session, project_id: int, commit_id: int):
    url = (f'{GITLAB_API_PREFIX}/projects/{project_id}/repository/'
           f'commits/{commit_id}/statuses')
    res = session.get(url)
    res.raise_for_status()
    return res.json()


def retry_job(session: Session, project_id: int, job_id: int):
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/jobs/{job_id}/retry'
    res = session.post(url)
    res.raise_for_status()
    return res.json()
