import re
import requests
from flask import Flask, request, abort
from requests import Session

from api.gitlab.issue import get_issue, update_issue
from api.gitlab.mr import (
    set_wip, get_mr_changes, update_mr, comment_mr
)
from api.gitlab.username import get_username
from constants import (
    NO_MD_CHANGELOG,
    MSG_BAD_BRANCH_NAME,
    MSG_MISSING_CHANGELOG,
    MSG_TKT_MR,
    REQUEST_TOKEN,
    SELF_USERNAME,
    TOKEN, GitlabLabels, regex_dict
)
from multi_main_repo_logic import handle_multi_main_push, notify_unmerged_superior_mrs, \
    add_multiple_merge_requests_label_if_needed
from utils import get_related_issue_iid, fill_fields_based_on_issue, has_label

app = Flask(__name__)

request_session = requests.Session()
request_session.headers['Private-Token'] = TOKEN


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
        return handle_push(request_session, json)

    if json['user']['username'] == SELF_USERNAME:
        # To prevent infinite loops and race conditions, ignore events related
        # to actions that this bot did
        return 'Ignoring webhook from myself'

    if json.get('object_kind') != 'merge_request':
        return 'I only process merge requests right now!'

    if has_label(json, GitlabLabels.SACATE_LA_GORRA):
        return 'Ignoring all!'

    mr = json['object_attributes']
    username = get_username(request_session, json)
    (project_id, iid) = (mr['source_project_id'], mr['iid'])

    is_multi_main = is_multi_main_mr(mr)

    check_issue_reference_in_description(request_session, mr)
    if is_multi_main:
        add_multiple_merge_requests_label_if_needed(request_session, mr)
    sync_related_issue(request_session, mr)
    fill_fields_based_on_issue(request_session, mr)

    branch_regex = regex_dict[mr['repository']['name']]
    if not re.match(branch_regex, mr['source_branch']):
        comment_mr(request_session, project_id, iid, f"@{username}: {MSG_BAD_BRANCH_NAME}", can_be_duplicated=False)

    if mr['work_in_progress']:
        return 'Ignoring WIP MR'
    if mr['state'] == 'merged' and is_multi_main:
        notify_unmerged_superior_mrs(request_session, mr)
    if mr['state'] in ('merged', 'closed'):
        return 'Ignoring closed MR'

    if has_label(json, GitlabLabels.NO_CHANGELOG):
        return f'Ignoring MR with label {GitlabLabels.NO_CHANGELOG}'

    print(f"Processing MR #{mr['iid']} of project {mr['repository']['name']}")

    if not has_changed_changelog(request_session, project_id, iid, only_md=True):
        if has_changed_changelog(request_session, project_id, iid, only_md=False):
            msg = NO_MD_CHANGELOG
        else:
            msg = MSG_MISSING_CHANGELOG
        comment_mr(request_session, project_id, iid, f"@{username}: {msg}")
        set_wip(request_session, project_id, iid)

    if mr['title'].lower().startswith('tkt '):
        comment_mr(request_session, project_id, iid, f"@{username}: {MSG_TKT_MR}", can_be_duplicated=False)

    return 'OK'


def handle_push(session: Session, push: dict):
    prefix = 'refs/heads/'
    if not push['ref'].startswith(prefix):  # TODO CHANGE FOR REACT AND OTHERS
        msg = f'Unknown ref name {push["ref"]}'
        print(msg)
        return msg

    if push["repository"]["name"] == "***REMOVED***":
        return handle_multi_main_push(session, push, prefix)

    return 'OK'


# @ehorvat: I believe this should be in a utils as it depends on gitlab
def has_changed_changelog(session: Session, project_id: int, iid: int, only_md: bool):
    changes = get_mr_changes(session, project_id, iid)
    changed_files = get_changed_files(changes)
    for filename in changed_files:
        if filename.startswith('CHANGELOG'):
            if not only_md or filename.endswith('.md'):
                return True
    return False


def get_changed_files(changes):
    return set(change['new_path'] for change in changes)


def sync_related_issue(session: Session, mr: dict):
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
    issue = get_issue(session, project_id, issue_iid)
    if issue is None or has_label(mr, GitlabLabels.MULTIPLE_MR):
        return

    close = False
    new_labels = issue['labels']
    try:
        new_labels.remove(GitlabLabels.TEST)
    except ValueError:
        pass
    try:
        new_labels.remove(GitlabLabels.ACCEPTED)
    except ValueError:
        pass

    if mr['work_in_progress']:
        new_labels.append(GitlabLabels.ACCEPTED)
    elif mr['state'] == 'opened' and not mr['work_in_progress']:
        new_labels.append(GitlabLabels.TEST)
    elif mr['state'] == 'merged':
        close = True
    elif mr['state'] == 'closed':
        pass

    new_labels = list(set(new_labels))
    data = {"labels": ','.join(new_labels)}
    if close:
        data['state_event'] = 'close'

    return update_issue(session, project_id, issue_iid, data)


def check_issue_reference_in_description(session: Session, mr: dict):
    issue_iid = get_related_issue_iid(mr)
    if issue_iid is None:
        return
    if f'#{issue_iid}' in mr['description']:
        # There is already a reference to the issue
        return
    project_id = mr['source_project_id']
    new_desc = f'Closes #{issue_iid} \r\n\r\n{mr["description"]}'
    return update_mr(session, project_id, mr['iid'], {'description': new_desc})


def is_multi_main_mr(mr):
    return mr["repository"]["name"] == "***REMOVED***"  # TODO CHANGE FOR REACT AND OTHERS


if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)
