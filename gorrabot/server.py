import re
from flask import Flask, request, abort

from gorrabot.api.gitlab import (
    GITLAB_REQUEST_TOKEN,
    GITLAB_SELF_USERNAME,
    GitlabLabels
)
from gorrabot.api.gitlab.issues import get_issue, update_issue
from gorrabot.api.gitlab.merge_requests import (
    set_wip,
    get_mr_changes,
    update_mr,
    comment_mr
)
from gorrabot.api.gitlab.usernames import get_username
from gorrabot.constants import (
    NO_MD_CHANGELOG,
    MSG_BAD_BRANCH_NAME,
    MSG_MISSING_CHANGELOG,
    MSG_TKT_MR,
    regex_dict
)
from gorrabot.multi_main_repo_logic import (
    handle_multi_main_push,
    notify_unmerged_superior_mrs,
    add_multiple_merge_requests_label_if_needed
)
from gorrabot.utils import get_related_issue_iid, fill_fields_based_on_issue, has_label

app = Flask(__name__)


@app.route('/status')
def status():
    return "OK"


@app.route('/webhook', methods=['POST'])
def homepage():
    if request.headers.get('X-Gitlab-Token') != GITLAB_REQUEST_TOKEN:
        abort(403)
    json = request.get_json()
    if json is None:
        abort(400)

    if json.get('object_kind') == 'push':
        return handle_push(json)

    if json['user']['username'] == GITLAB_SELF_USERNAME:
        # To prevent infinite loops and race conditions, ignore events related
        # to actions that this bot did
        return 'Ignoring webhook from myself'

    if json.get('object_kind') != 'merge_request':
        return 'I only process merge requests right now!'

    if has_label(json, GitlabLabels.SACATE_LA_GORRA):
        return 'Ignoring all!'

    mr_json = json
    mr_attributes = mr_json['object_attributes']
    username = get_username(mr_json)
    (project_id, iid) = (mr_attributes['source_project_id'], mr_attributes['iid'])

    is_multi_main = is_multi_main_mr(mr_json)

    check_issue_reference_in_description(mr_json)
    if is_multi_main:
        add_multiple_merge_requests_label_if_needed(mr_json)
    sync_related_issue(mr_json)
    fill_fields_based_on_issue(mr_json)

    branch_regex = regex_dict[mr_json['repository']['name']]
    if not re.match(branch_regex, mr_attributes['source_branch']):
        comment_mr(project_id, iid, f"@{username}: {MSG_BAD_BRANCH_NAME}", can_be_duplicated=False)

    if mr_attributes['work_in_progress']:
        return 'Ignoring WIP MR'
    if mr_attributes['state'] == 'merged' and is_multi_main:
        notify_unmerged_superior_mrs(mr_json)
    if mr_attributes['state'] in ('merged', 'closed'):
        return 'Ignoring closed MR'

    if has_label(mr_json, GitlabLabels.NO_CHANGELOG):
        return f'Ignoring MR with label {GitlabLabels.NO_CHANGELOG}'

    print(f"Processing MR #{mr_attributes['iid']} of project {mr_json['repository']['name']}")

    if not has_changed_changelog(project_id, iid, only_md=True):
        if has_changed_changelog(project_id, iid, only_md=False):
            msg = NO_MD_CHANGELOG
        else:
            msg = MSG_MISSING_CHANGELOG
        comment_mr(project_id, iid, f"@{username}: {msg}")
        set_wip(project_id, iid)

    if mr_attributes['title'].lower().startswith('tkt '):
        comment_mr(project_id, iid, f"@{username}: {MSG_TKT_MR}", can_be_duplicated=False)

    return 'OK'


def handle_push(push: dict):
    prefix = 'refs/heads/'
    if not push['ref'].startswith(prefix):  # TODO CHANGE FOR REACT AND OTHERS
        msg = f'Unknown ref name {push["ref"]}'
        print(msg)
        return msg

    if push["repository"]["name"] == "***REMOVED***":
        return handle_multi_main_push(push, prefix)

    return 'OK'


# @ehorvat: I believe this should be in a utils as it depends on gitlab
def has_changed_changelog(project_id: int, iid: int, only_md: bool):
    changes = get_mr_changes(project_id, iid)
    changed_files = get_changed_files(changes)
    for filename in changed_files:
        if filename.startswith('CHANGELOG'):
            if not only_md or filename.endswith('.md'):
                return True
    return False


def get_changed_files(changes):
    return set(change['new_path'] for change in changes)


def sync_related_issue(mr_json: dict):
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
    mr = mr_json["object_attributes"]
    issue_iid = get_related_issue_iid(mr_json)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    issue = get_issue(project_id, issue_iid)
    if issue is None or has_label(mr_json, GitlabLabels.MULTIPLE_MR):
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

    return update_issue(project_id, issue_iid, data)


def check_issue_reference_in_description(mr_json: dict):
    mr = mr_json["object_attributes"]
    issue_iid = get_related_issue_iid(mr_json)
    if issue_iid is None:
        return
    if f'#{issue_iid}' in mr['description']:
        # There is already a reference to the issue
        return
    project_id = mr['source_project_id']
    new_desc = f'Closes #{issue_iid} \r\n\r\n{mr["description"]}'
    return update_mr(project_id, mr['iid'], {'description': new_desc})


def is_multi_main_mr(mr_json):
    return mr_json["repository"]["name"] == "***REMOVED***"  # TODO CHANGE FOR REACT AND OTHERS


def main():
    app.run(debug=True, use_reloader=True)


if __name__ == '__main__':
    main()
