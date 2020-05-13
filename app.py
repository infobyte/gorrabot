import re
import datetime
import requests
from urllib.parse import quote
from flask import Flask, request, abort

from api.gitlab.mr import (
    get_merge_requests,
    set_wip
)
from api.gitlab.username import get_username
from constants import (
    branch_regex,
    decision_issue_message_interval,
    NO_MD_CHANGELOG,
    MSG_BAD_BRANCH_NAME,
    MSG_CHECK_SUPERIOR_MR,
    MSG_MISSING_CHANGELOG,
    MSG_TKT_MR,
    REQUEST_TOKEN,
    SELF_USERNAME,
    TOKEN, GitlabLabels
)
from multi_main_repo_logic import handle_multi_main_push

app = Flask(__name__)

session = requests.Session()
session.headers['Private-Token'] = TOKEN


@app.route('/status')
def status():
    return "OK"


@app.route('/webhook', methods=['POST'])
def homepage():
    if request.headers.get('X-Gitlab-Token') != REQUEST_TOKEN:
        abort(403)
    json = request.get_json()
    if json is None:
        abort(400)

    if json.get('object_kind') == 'push':
        return handle_push(json)

    if json['user']['username'] == SELF_USERNAME:
        # To prevent infinite loops and race conditions, ignore events related
        # to actions that this bot did
        return 'Ignoring webhook from myself'

    if json.get('object_kind') != 'merge_request':
        return 'I only process merge requests right now!'

    if has_label(json, 'sacate-la-gorra'):
        return 'Ignoring all!'

    mr = json['object_attributes']
    username = get_username(session, json)
    (project_id, iid) = (mr['source_project_id'], mr['iid'])

    check_issue_reference_in_description(mr)
    add_multiple_merge_requests_label_if_needed(mr)
    sync_related_issue(mr)
    fill_fields_based_on_issue(mr)

    if not re.match(branch_regex, mr['source_branch']):
        comment_mr(project_id, iid, "@{}: {}".format(
            username, MSG_BAD_BRANCH_NAME), can_be_duplicated=False)

    if mr['work_in_progress']:
        return 'Ignoring WIP MR'
    if mr['state'] == 'merged':
        notify_unmerged_superior_mrs(mr)
    if mr['state'] in ('merged', 'closed'):
        return 'Ignoring closed MR'

    if has_label(json, GitlabLabels.NO_CHANGELOG):
        return f'Ignoring MR with label {GitlabLabels.NO_CHANGELOG}'

    print("Processing MR #", mr['iid'])

    if not has_changed_changelog(project_id, iid, only_md=True):
        if has_changed_changelog(project_id, iid, only_md=False):
            msg = NO_MD_CHANGELOG
        else:
            msg = MSG_MISSING_CHANGELOG
        comment_mr(project_id, iid, "@{}: {}".format(
            username, msg))
        set_wip(session, project_id, iid)

    if mr['title'].lower().startswith('tkt '):
        comment_mr(project_id, iid, "@{}: {}".format(
            username, MSG_TKT_MR), can_be_duplicated=False)

    return 'OK'


def handle_push(push):
    prefix = 'refs/heads/'
    if not push['ref'].startswith(prefix):
        msg = f'Unknown ref name {push["ref"]}'
        print(msg)
        return msg

    if push["repository"]["name"] == "***REMOVED***":
        return handle_multi_main_push(push, prefix)

    return 'OK'


def has_label(obj, label_name):
    return any(label['title'] == label_name
               for label in obj.get('labels', []))


# HERE
def has_changed_changelog(project_id, iid, only_md):
    changes = get_mr_changes(session,project_id, iid)
    changed_files = get_changed_files(changes)
    for filename in changed_files:
        if filename.startswith('CHANGELOG'):
            if not only_md or filename.endswith('.md'):
                return True
    return False


def get_branch_last_commit(project_id, branch_name):
    branch = get_branch(project_id, branch_name)
    if branch is None:
        return
    return branch['commit']


def get_changed_files(changes):
    return set(change['new_path'] for change in changes)


def sync_related_issue(mr):
    """Change the status of the issue related to the new/updated MR

    Get the issue by matching the source branch name. If the issue has
    the multiple-merge-requests label, do nothing.

    WIP MR -> Label issue as accepted
    Pending merge/approval MR -> Label issue as test
    Merged MR -> Close issue and delete status labels (accepted, test)
    # Closed MR -> Close issue, delete status label and label as invalid
    # Closed MR -> Do nothing, assume that another MR will be created
    Closed MR -> Delete status labels (set to new)
    """

    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    issue = get_issue(project_id, issue_iid)
    if issue is None or has_label(mr, 'multiple-merge-requests'):
        return

    close = False
    new_labels = issue['labels']
    try:
        new_labels.remove('Test')
    except ValueError:
        pass
    try:
        new_labels.remove('Accepted')
    except ValueError:
        pass

    if mr['work_in_progress']:
        new_labels.append('Accepted')
    elif mr['state'] == 'opened' and not mr['work_in_progress']:
        new_labels.append('Test')
    elif mr['state'] == 'merged':
        close = True
    elif mr['state'] == 'closed':
        pass

    new_labels = list(set(new_labels))
    data = {"labels": ','.join(new_labels)}
    if close:
        data['state_event'] = 'close'

    return update_issue(project_id, issue_iid, data)


def fill_fields_based_on_issue(mr):
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
        assignee_id = mr['assignee'] and mr['assignee']['id'] # TODO CONTROL

    if milestone_id is None and issue.get('milestone'):
        data['milestone_id'] = issue['milestone']['id']
    if assignee_id is None and len(issue.get('assignees', [])) == 1:
        data['assignee_id'] = issue['assignees'][0]['id'] # TODO CHANGE

    if data:
        return update_mr(project_id, mr['iid'], data)


def check_issue_reference_in_description(mr):
    issue_iid = get_related_issue_iid(mr)
    if issue_iid is None:
        return
    if f'#{issue_iid}' in mr['description']:
        # There is already a reference to the issue
        return
    project_id = mr['source_project_id']
    new_desc = f'Closes #{issue_iid} \r\n\r\n{mr["description"]}'
    return update_mr(project_id, mr['iid'], {'description': new_desc})


def add_multiple_merge_requests_label_if_needed(mr):
    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    if mr['state'] == 'closed':
        # Not adding this could mail the assertion below fail
        return

    related_mrs = get_related_merge_requests(
        mr['source_project_id'], issue_iid)

    # Discard closed merge requests, maybe they were created
    # accidentally and then closed
    related_mrs = [rmr for rmr in related_mrs
                   if rmr['state'] != 'closed']

    # Some MRs could be related to an issue only because they mentioned it,
    # not because they are implementing that issue
    related_mrs = [rmr for rmr in related_mrs
                   if str(issue_iid) in mr['source_branch']]

    assert any(rmr['iid'] == mr['iid']
               for rmr in related_mrs)

    if len(related_mrs) > 1:
        issue = get_issue(project_id, issue_iid)
        if issue is None or has_label(mr, 'multiple-merge-requests'):
            return
        new_labels = issue['labels']
        new_labels.append('multiple-merge-requests')
        new_labels = list(set(new_labels))
        data = {"labels": ','.join(new_labels)}
        return update_issue(project_id, issue_iid, data)


def notify_unmerged_superior_mrs(mr):
    """Warn the user who merged mr if there also are ***REMOVED*** or ***REMOVED*** merge
    requests for the same issue."""
    assert mr['state'] == 'merged'
    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return

    related_mrs = get_related_merge_requests(
        project_id, issue_iid)
    related_mrs = [rmr for rmr in related_mrs
                   if rmr['state'] not in ('merged', 'closed')]

    if '***REMOVED***' in mr['source_branch']:
        expected_versions = ['***REMOVED***', '***REMOVED***']
    elif '***REMOVED***' in mr['source_branch']:
        expected_versions = ['***REMOVED***']
    else:
        expected_versions = []

    global_branch_name = remove_version(mr['source_branch'])

    # Discard MRs with different branch names (besides ***REMOVED***/***REMOVED***/***REMOVED***)
    related_mrs = [
        rmr for rmr in related_mrs
        if remove_version(rmr['source_branch']) == global_branch_name
    ]

    # Discard MRs that are not of expected_versions
    related_mrs = [
        rmr for rmr in related_mrs
        if any(version in rmr['source_branch']
               for version in expected_versions)
    ]

    # The data from the webhook doesn't contain merged_by
    mr = get_mr(project_id, mr['iid'])

    username = mr['merged_by']['username']
    for rmr in related_mrs:
        comment_mr(
            project_id,
            rmr['iid'],
            f'@{username}: {MSG_CHECK_SUPERIOR_MR}',
            can_be_duplicated=False,
        )


def remove_version(branch: str):
    return branch.replace('***REMOVED***', 'xxx').replace('***REMOVED***', 'xxx').replace('***REMOVED***', 'xxx')


def filter_current_or_upcoming_mrs(merge_requests):
    for mr in merge_requests:
        milestone = mr['milestone']
        if not milestone:
            continue
        if milestone['state'] != 'active':
            continue
        if ('upcoming' in milestone['title'] or
                'current' in milestone['title']):
            yield mr


def get_related_issue_iid(mr):
    branch = mr['source_branch']
    try:
        iid = re.findall(branch_regex, branch)[0]
    except IndexError:
        return
    return int(iid)



def get_branch(project_id, branch_name):
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/repository/branches/{quote(branch_name, safe="")}'
    res = session.get(url)
    if res.status_code == 404:
        return
    res.raise_for_status()
    return res.json()


def get_commit_jobs(project_id, commit_id):
    url = (f'{GITLAB_API_PREFIX}/projects/{project_id}/repository/'
           f'commits/{commit_id}/statuses')
    res = session.get(url)
    res.raise_for_status()
    return res.json()


def retry_job(project_id, job_id):
    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/jobs/{job_id}/retry'
    res = session.post(url)
    res.raise_for_status()
    return res.json()


def update_issue(project_id, iid, data):
    url = '{}/projects/{}/issues/{}'.format(
            GITLAB_API_PREFIX, project_id, iid)
    res = session.put(url, json=data)
    res.raise_for_status()
    return res.json()


if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
