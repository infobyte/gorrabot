import datetime
import logging

from gorrabot.api.gitlab import gitlab_session, GITLAB_API_PREFIX
from gorrabot.api.gitlab.projects import get_project_name
from gorrabot.api.gitlab.utils import paginated_get
from gorrabot.api.utils import parse_api_date
from gorrabot.config import config

logger = logging.getLogger(__name__)


def get_merge_requests(project_id: int, filters=None):
    if filters is None:
        filters = {}
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/merge_requests'
    return paginated_get(url, filters)


def mr_url(project_id, iid):
    return '{}/projects/{}/merge_requests/{}'.format(
            GITLAB_API_PREFIX, project_id, iid)


def get_mr_changes(project_id: int, iid: int):
    url = mr_url(project_id, iid) + '/changes'
    res = gitlab_session.get(url)
    res.raise_for_status()
    return res.json()['changes']


def get_mr(project_id: int, iid: int):
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/merge_requests/{iid}'
    res = gitlab_session.get(url)
    res.raise_for_status()
    return res.json()


def get_mr_last_commit(mr: dict):
    project_id = mr['source_project_id']
    url = mr_url(project_id, mr['iid']) + '/commits'
    res = gitlab_session.get(url)
    res.raise_for_status()
    try:
        return res.json()[0]
    except IndexError:
        return


def create_mr(project_id: int, mr_data: dict):
    url = (
        f"{GITLAB_API_PREFIX}/projects/{project_id}/"
        f"merge_requests"
    )
    res = gitlab_session.post(url, json=mr_data)
    res.raise_for_status()
    return res.json()


def set_wip(project_id: int, iid: int):
    url = mr_url(project_id, iid)
    res = gitlab_session.get(url)
    res.raise_for_status()
    mr = res.json()

    if not mr['work_in_progress'] and not mr['title'].startswith('WIP:') and not mr['title'].startswith('Draft:'):
        data = {"title": "Draft: " + mr['title']}
        update_mr(project_id, iid, data)
    else:
        logger.info("Is currently in WIP/Draft")


def update_mr(project_id: int, iid: int, data: dict):
    url = mr_url(project_id, iid)
    res = gitlab_session.put(url, json=data)
    res.raise_for_status()
    return res.json()


def get_related_merge_requests(project_id: int, issue_iid: int):
    url = '{}/projects/{}/issues/{}/related_merge_requests'.format(
            GITLAB_API_PREFIX, project_id, issue_iid)
    return paginated_get(url)


def comment_mr(project_id: int, iid: int, body: str, can_be_duplicated=True, min_time_between_comments=None):
    project_name = get_project_name(project_id)
    comment_mr = config[project_name].get('comment_mr', None)
    if not (comment_mr or isinstance(comment_mr, bool)):
        return
    if not can_be_duplicated:
        # Ugly hack to drop user mentions from body
        search_title = body.split(': ', 1)[-1]
        res = gitlab_session.get(mr_url(project_id, iid) + '/notes')
        res.raise_for_status()
        comments = res.json()
        if any(search_title in comment['body']
                for comment in comments):
            # This comment has already been made
            return
    elif min_time_between_comments is not None:
        # The comment can be duplicated, but to avoid flooding, wait at least
        # min_time_between_comments to duplicate them
        # Ugly hack to drop user mentions from body
        search_title = body.split(': ', 1)[-1]
        res = gitlab_session.get(mr_url(project_id, iid) + '/notes')
        res.raise_for_status()
        comments = res.json()

        def is_recent_comment(comment):
            time_passed = datetime.datetime.utcnow() - parse_api_date(comment['created_at'])
            return time_passed < min_time_between_comments

        if any(is_recent_comment(comment) and
               search_title.strip() in comment['body'].strip()
               for comment in comments):
            return

    url = mr_url(project_id, iid) + '/notes'
    data = {"body": body}
    res = gitlab_session.post(url, json=data)
    res.raise_for_status()
    return res.json()
