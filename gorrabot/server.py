import os
from typing import NoReturn, List
import logging
import re
import sys

import flask
from flask import Flask, request, abort

from gorrabot.api.constants import gitlab_to_slack_user_dict
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
from gorrabot.api.slack.messages import send_message_to_error_channel, send_debug_message
from gorrabot.config import config
from gorrabot.constants import (
    NO_MD_CHANGELOG,
    MSG_BAD_BRANCH_NAME,
    MSG_MISSING_CHANGELOG,
    MSG_TKT_MR,
    regex_dict, MSG_WITHOUT_PRIORITY, MSG_WITHOUT_SEVERITY, MSG_WITHOUT_WEIGHT, MSG_NOTIFICATION_PREFIX_WITH_USER,
    MSG_NOTIFICATION_PREFIX_WITHOUT_USER
)
from gorrabot.multi_main_repo_logic import (
    handle_multi_main_push,
    notify_unmerged_superior_mrs,
    add_multiple_merge_requests_label_if_needed
)
from gorrabot.utils import get_related_issue_iid, fill_fields_based_on_issue, has_label

app = Flask(__name__)

# Logging set to stdout
root = logging.getLogger()
root.setLevel(logging.DEBUG if 'DEBUG' in os.environ else logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG if 'DEBUG' in os.environ else logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)
logger = logging.getLogger(__name__)


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
        logger.info("Handling a PUSH event")
        send_debug_message("Handling a PUSH event")
        return handle_push(json)

    if json['user']['username'] == GITLAB_SELF_USERNAME:
        # To prevent infinite loops and race conditions, ignore events related
        # to actions that this bot did
        logger.info('Ignoring webhook from myself')
        send_debug_message('Ignoring webhook from myself')
        return 'Ignoring webhook from myself'

    if json.get('object_kind') != 'merge_request':
        logger.info('I only process merge requests right now!')
        send_debug_message('I only process merge requests right now!')
        return 'I only process merge requests right now!'

    logger.info("Handling a MR event")
    send_debug_message("Handling a MR event")
    return handle_mr(json)


def handle_push(push: dict) -> str:
    prefix = 'refs/heads/'

    if not push['ref'].startswith(prefix):
        msg = f'Unknown ref name {push["ref"]}'
        print(msg)
        return msg

    project_name = push["repository"]["name"]
    if project_name not in config:
        send_message_to_error_channel(
            text=f"The project `{project_name}` tried to use gorrabot's webhook, but its not in the configuration"
        )
        return flask.abort(400, "project not in the configuration")

    branch_regex = regex_dict[project_name]
    branch_name = push['ref'][len(prefix):]

    if not re.match(branch_regex, branch_name):
        if not re.match(r"^((dev|master)|(.*/(dev|master)))$", branch_name):
            logger.warning("Branch does not match with regex")
            send_debug_message("Branch does not match with regex")
            send_message_to_error_channel(f"Unexpected push to `{project_name}`, branch `{branch_name}` do not follow "
                                          "expected regex format")
        else:
            logger.info("dev or master branch")
            send_debug_message("dev or master branch")
    else:
        check_labels_and_weight(push, branch_name)
        if 'multi-branch' in config[project_name]:
            return handle_multi_main_push(push, prefix)

    return 'OK'


def handle_mr(mr_json: dict) -> str:
    if has_label(mr_json, GitlabLabels.SACATE_LA_GORRA):
        logger.warning('Ignoring because of label flag')
        send_debug_message('Ignoring because of label flag')
        return 'Ignoring all!'

    mr_attributes = mr_json['object_attributes']
    project_name = mr_json["repository"]["name"]

    if project_name not in config:
        logger.warning('Project not in the configuration')
        send_debug_message('Project not in the configuration')
        send_message_to_error_channel(
            text=f"The project `{project_name}` tried to use gorrabot's webhook, but its not in the configuration"
        )
        return flask.abort(400, "Project not in the configuration")

    username = get_username(mr_json)
    (project_id, iid) = (mr_attributes['source_project_id'], mr_attributes['iid'])

    branch_regex = regex_dict[mr_json['repository']['name']]
    if not re.match(branch_regex, mr_attributes['source_branch']):
        logger.info("Branch do not match regex")
        send_debug_message("Branch do not match regex")
        msg_bad_branch_name = MSG_BAD_BRANCH_NAME.format(main_branches=config[project_name]['multi-branch'])
        comment_mr(project_id, iid, f"@{username}: {msg_bad_branch_name}", can_be_duplicated=False)

    is_multi_main = is_multi_main_mr(mr_json)

    print(f"Processing MR #{mr_attributes['iid']} of project {mr_json['repository']['name']}")

    check_status(mr_json, project_name)
    check_issue_reference_in_description(mr_json)
    if is_multi_main:
        add_multiple_merge_requests_label_if_needed(mr_json)
    sync_related_issue(mr_json)
    fill_fields_based_on_issue(mr_json)

    if mr_attributes['state'] == 'merged' and is_multi_main:
        logger.info("Notifying a Merge to superiors main branches")
        send_debug_message("Notifying a Merge to superiors main branches")
        notify_unmerged_superior_mrs(mr_json, project_name)
    if mr_attributes['state'] in ('merged', 'closed'):
        logger.info("Ignoring because of close status")
        send_debug_message("Ignoring because of close status")
        return 'Ignoring closed MR'

    if mr_attributes['title'].lower().startswith('tkt '):
        comment_mr(project_id, iid, f"@{username}: {MSG_TKT_MR}", can_be_duplicated=False)

    return 'OK'


def check_status(mr_json: dict, project_name: str) -> NoReturn:
    if (
            has_label(mr_json, GitlabLabels.NO_CHANGELOG) or
            ('flags' in config[project_name] and
             "NO_CHANGELOG" in [flag.upper() for flag in config[project_name]['flags']]
             )
    ):
        logger.info('Ignoring MR Changelog')
        send_debug_message('Ignoring MR Changelog')
        return
    mr_attributes = mr_json['object_attributes']
    (project_id, iid) = (mr_attributes['source_project_id'], mr_attributes['iid'])
    username = get_username(mr_json)

    if not has_changed_changelog(project_id, iid, project_name, only_md=True):
        if has_changed_changelog(project_id, iid, project_name, only_md=False):
            msg = NO_MD_CHANGELOG
        else:
            msg = MSG_MISSING_CHANGELOG
        comment_mr(project_id, iid, f"@{username}: {msg}")
        set_wip(project_id, iid)
        mr_attributes['work_in_progress'] = True


def check_labels_and_weight(push: dict, branch_name: str) -> NoReturn:
    project_name = push["repository"]["name"]
    branch_regex = regex_dict[project_name]
    issue_iid = re.match(branch_regex, branch_name).group("iid")
    project_id = push['project_id']
    issue = get_issue(project_id, issue_iid)
    messages = []
    labels: List[str] = issue['labels']
    if all([not label.startswith("priority::") for label in labels]):
        logger.info("No priority label found")
        messages.append(MSG_WITHOUT_PRIORITY)
    if all([not label.startswith("severity::") for label in labels]):
        logger.info("No severity label found")
        messages.append(MSG_WITHOUT_SEVERITY)
    weight = issue['weight']
    if weight is None:
        logger.info("Weight found")
        messages.append(MSG_WITHOUT_WEIGHT)
    if len(messages) > 0:
        error_message_list = '\n    * '.join([''] + messages)
        username = push["user_username"]
        if username in gitlab_to_slack_user_dict:
            error_message = MSG_NOTIFICATION_PREFIX_WITH_USER.format(
                user=gitlab_to_slack_user_dict[username],
                branch=branch_name)
        else:
            error_message = MSG_NOTIFICATION_PREFIX_WITHOUT_USER.format(user=username, branch=branch_name)

        error_message = f"{error_message}{error_message_list}"
        send_message_to_error_channel(error_message)


# @ehorvat: I believe this should be in a utils as it depends on gitlab
def has_changed_changelog(project_id: int, iid: int, project_name, only_md: bool):
    changes = get_mr_changes(project_id, iid)
    changed_files = get_changed_files(changes)
    for filename in changed_files:
        if filename.startswith('CHANGELOG'):
            valid_ext = config[project_name]['changelog_filetype'] if 'changelog_filetype' in config[project_name] \
                                                                   else '.md'
            if not only_md or filename.endswith(valid_ext):
                return True
            else:
                if 'changelog_exceptions' in config[project_name]:
                    _, file_name = os.path.split(filename)
                    if file_name in config[project_name]['changelog_exceptions']:
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
    elif mr['state'] == 'opened':
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
    return 'multi-branch' in config[mr_json["repository"]["name"]]


def main():
    app.run(debug=True, use_reloader=True)


if __name__ == '__main__':
    main()
