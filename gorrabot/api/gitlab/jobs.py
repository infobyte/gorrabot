from gorrabot.api.gitlab import gitlab_session,GITLAB_API_PREFIX
from gorrabot.api.gitlab.utils import paginated_get


def get_commit_jobs(project_id: int, commit_id: int):
    url = (f'{GITLAB_API_PREFIX}/projects/{project_id}/repository/'
           f'commits/{commit_id}/statuses')
    return paginated_get(url)


def retry_job(project_id: int, job_id: int):
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/jobs/{job_id}/retry'
    res = gitlab_session.post(url)
    res.raise_for_status()
    return res.json()
