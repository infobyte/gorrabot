import datetime
import logging
from typing import List
import re

from gorrabot.api.gitlab import GitlabLabels
from gorrabot.api.gitlab.branches import get_branch
from gorrabot.api.gitlab.issues import get_issue, get_issues, get_accepted_issues
from gorrabot.api.gitlab.merge_requests import update_mr, get_merge_requests, get_mr_changes, get_mr, \
    get_mr_last_commit, get_related_merge_requests
from gorrabot.api.gitlab.projects import get_project_name
from gorrabot.api.utils import parse_api_date
from gorrabot.config import config
from gorrabot.constants import regex_dict, decision_issue_message_interval, inactivity_time
import json
logger = logging.getLogger(__name__)


def has_label(obj, label_name):
    return any(label['title'] == label_name
               for label in obj.get('labels', []))


def has_flag(project_name, passed_flag):
    has_flag_attr = 'flags' in config()['projects'][project_name]
    param_list = ['NO_CHANGELOG', 'NO_PRIORITY', 'NO_SEVERITY']
    has_passed_flag = False

    if not has_flag_attr:
        logger.warning("'Flags' attribute not detected. Proceeding to verify there is changelog")
        return has_flag_attr and has_passed_flag

    if passed_flag in param_list:
        selected_flag = param_list[param_list.index(passed_flag)]
        has_passed_flag = selected_flag in [flag.upper() for flag in config()['projects'][project_name]['flags']]
    else:
        logger.warning('Passed flag was not recognized. Proceeding to verify there is changelog')

    return has_flag_attr and has_passed_flag


def get_related_issue_iid(mr: dict):
    branch = mr['source_branch'] if "source_branch" in mr else mr["object_attributes"]["source_branch"]
    project_id = mr["project_id"] if "project_id" in mr else mr["project"]["id"]
    project_name = get_project_name(project_id)
    branch_regex = regex_dict[project_name]
    try:
        iid = re.match(branch_regex, branch).group('iid')
    except (IndexError, AttributeError):
        return

    try:
        return int(iid)
    except ValueError:
        return None


def filter_current_or_upcoming_mrs(merge_requests: List[dict]):
    for mr in merge_requests:
        milestone = mr['milestone']
        if not milestone:
            continue
        if milestone['state'] != 'active':
            continue
        if milestone['title'].lower() in ['upcoming', 'current']:
            yield mr


def get_branch_last_commit(project_id: int, branch_name: str):
    branch = get_branch(project_id, branch_name)
    if branch is None:
        return
    return branch['commit']


def fill_fields_based_on_issue(mr_json: dict):
    """Complete the MR fields with data in its associated issue.

    If the MR doesn't have an assigned user, set to the issue's
    assignee.

    If the MR doesn't have a milestone, set it to the issue's
    milestone. Also update it.
    """
    mr = mr_json["object_attributes"] if "object_attributes" in mr_json else mr_json
    issue_iid = get_related_issue_iid(mr_json)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    issue = get_issue(project_id, issue_iid)
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

    if issue.get('milestone'):
        data['milestone_id'] = issue['milestone']['id']
    if assignee_id is None and len(issue.get('assignees', [])) == 1:
        data['assignee_id'] = issue['assignees'][0]['id']  # TODO CHANGE

    if data:
        return update_mr(project_id, mr['iid'], data)


def get_decision_issues(project_id: int):
    filters = {
        'scope': 'all',
        'state': 'opened',
        'labels': 'waiting-decision',
        'per_page': 100,
    }
    issues = get_issues(project_id, filters)
    for issue in issues:
        if GitlabLabels.DONT_RUSH_ME in issue['labels']:
            continue
        updated_at = parse_api_date(issue['updated_at'])
        if datetime.datetime.utcnow() - updated_at > decision_issue_message_interval:
            yield issue


def get_waiting_users_from_issue(issue):
    description = issue["description"]
    desc_lines = [line.strip() for line in description.splitlines()]
    match = list(filter(lambda line: re.match(r"WFD: .+", line), desc_lines))
    users = []
    if len(match) > 0:
        users = [user.strip() for user in match[0][4:].split(",")]

    return users


def get_staled_merge_requests(project_id: int, wip=None):
    filters = {
        'scope': 'all',
        'wip': wip,
        'state': 'opened',
        'per_page': 100,
    }
    mrs = get_merge_requests(project_id, filters)
    for mr in mrs:
        if GitlabLabels.DONT_RUSH_ME in mr['labels']:
            continue
        if mr['source_branch'] and mr['source_branch'].startswith('exp_'):
            continue
        last_commit = get_mr_last_commit(mr)
        if last_commit is None:
            # There is no activity in the MR, use the MR's creation date
            created_at = parse_api_date(mr['created_at'])
        else:
            created_at = parse_api_date(last_commit['created_at'])
        if datetime.datetime.utcnow() - created_at > inactivity_time:
            yield mr


def get_push_info(push, branch_name):
    """ Gets several attributes from the PR's json """
    project_name = push["repository"]["name"]
    branch_regex = regex_dict[project_name]
    issue_iid = re.match(branch_regex, branch_name).group("iid")
    project_id = push['project_id']

    push_info = {
        "project_name": project_name,
        "branch_regex": branch_regex,
        "issue_iid": issue_iid,
        "project_id": project_id
    }

    return push_info


def create_report(notify_dict: dict, user: str):
    accepted_issues = report_accepted_issues(notify_dict[user]["accepted-issues"])
    report = f"""*{user}*
    •stale_wip: {len(notify_dict[user]["stale_wip"])}
    •stale_no_wip: {len(notify_dict[user]["stale_no_wip"])}
    •waiting-decision: {len(notify_dict[user]["waiting-decision"])}
    •accepted-issues: 
        Estimated:{accepted_issues['Estimated']}
        Not Estimated:{accepted_issues['Not Estimated']}
    """
    return report


def report_accepted_issues(accepted_issues: list):
    issues = {
        'Estimated': [],
        'Not Estimated': []
    }
    for issue in accepted_issues:
        if issue['time_stats']['human_time_estimate'] is None:
            issues['Not Estimated'].append(issue['web_url'])
        else:
            issues['Estimated'].append({
                'id': issue['web_url'],
                'Estimated': issue['time_stats']['human_time_estimate'],
                'Spent': issue['time_stats']['human_total_time_spent'],
            })
    return issues


def clear_cached_functions():
    get_branch.cache_clear()
    get_issue.cache_clear()
    get_merge_requests.cache_clear()
    get_mr_changes.cache_clear()
    get_related_merge_requests.cache_clear()