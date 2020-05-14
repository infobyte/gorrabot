from typing import List
import re
from requests import Session

from api.gitlab.branch import get_branch
from api.gitlab.issue import get_issue
from api.gitlab.mr import update_mr
from constants import regex_dict


def has_label(obj, label_name):
    return any(label['title'] == label_name
               for label in obj.get('labels', []))


def get_related_issue_iid(mr: dict):
    branch = mr['source_branch']
    branch_regex = regex_dict[mr['repository']['name']]
    try:
        iid = re.findall(branch_regex, branch)[0]
    except IndexError:
        return
    return int(iid)


def filter_current_or_upcoming_mrs(merge_requests: List[dict]):
    for mr in merge_requests:
        milestone = mr['milestone']
        if not milestone:
            continue
        if milestone['state'] != 'active':
            continue
        if milestone['title'].lower() in ['upcoming', 'current']:
            yield mr


def get_branch_last_commit(session: Session, project_id: int, branch_name: str):
    branch = get_branch(session, project_id, branch_name)
    if branch is None:
        return
    return branch['commit']


def fill_fields_based_on_issue(session: Session, mr: dict):
    """Complete the MR fields with data in its associated issue.

    If the MR doesn't have an assigned user, set to the issue's
    assignee.

    If the MR doesn't have a milestone, set it to the issue's
    milestone.
    """

    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    issue = get_issue(session, project_id, issue_iid)
    if issue is None:
        return

    data = {}

    if 'milestone_id' in mr:
        # This comes from the webhook data
        milestone_id = mr['milestone_id']
    else:
        milestone_id = mr['milestone'] and mr['milestone']['id']

    if 'assignee_id' in mr:
        # This comes from the webhook data
        assignee_id = mr['assignee_id']
    else:
        assignee_id = mr['assignee'] and mr['assignee']['id']  # TODO CONTROL

    if milestone_id is None and issue.get('milestone'):
        data['milestone_id'] = issue['milestone']['id']
    if assignee_id is None and len(issue.get('assignees', [])) == 1:
        data['assignee_id'] = issue['assignees'][0]['id']  # TODO CHANGE

    if data:
        return update_mr(session, project_id, mr['iid'], data)
