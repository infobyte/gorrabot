import os
from typing import NoReturn, List
import logging
import re
import sys

import flask
from flask import Flask, request, abort, make_response

from gorrabot.api.constants import gitlab_to_slack_user_dict
from gorrabot.api.gitlab import (
    GITLAB_REQUEST_TOKEN,
    GITLAB_SELF_USERNAME,
    GitlabLabels,
    GITLAB_API_PREFIX,
    gitlab_session
)
from gorrabot.api.gitlab.issues import get_issue, update_issue
from gorrabot.api.gitlab.merge_requests import (
    set_wip,
    get_mr_changes,
    update_mr,
    comment_mr
)
from gorrabot.api.gitlab.usernames import get_username
from gorrabot.api.gitlab.utils import paginated_get
from gorrabot.api.slack.messages import send_message_to_error_channel, send_debug_message
from gorrabot.config import config, DEBUG_MODE, config
from gorrabot.constants import (
    NO_VALID_CHANGELOG_FILETYPE,
    MSG_BAD_BRANCH_NAME,
    MSG_MISSING_CHANGELOG,
    MSG_TKT_MR,
    regex_dict, MSG_WITHOUT_PRIORITY, MSG_WITHOUT_SEVERITY, MSG_WITHOUT_WEIGHT, MSG_NOTIFICATION_PREFIX_WITH_USER,
    MSG_NOTIFICATION_PREFIX_WITHOUT_USER,
    MSG_WITHOUT_MILESTONE,
    BACKLOG_MILESTONE,
    MSG_BACKLOG_MILESTONE,
    MSG_WITHOUT_ITERATION
)
from gorrabot.multi_main_repo_logic import (
    handle_multi_main_push,
    notify_unmerged_superior_mrs,
    add_multiple_merge_requests_label_if_needed
)
from gorrabot.utils import get_related_issue_iid, fill_fields_based_on_issue, has_label, has_flag, get_push_info
from gorrabot.timer import GorrabotTimer

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



@app.route('/clear-cache')
def clear_vault_cache():
    if not DEBUG_MODE and request.headers.get('X-Gitlab-Token') != GITLAB_REQUEST_TOKEN:
        abort(403)
    logger.info("Clearing Vault cache...")
    config.cache_clear()
    return "OK"


@app.route('/status')
def status():
    return "OK"


@app.route('/webhook', methods=['POST'])
def homepage():
    if not DEBUG_MODE and request.headers.get('X-Gitlab-Token') != GITLAB_REQUEST_TOKEN:
        abort(403)
    json = request.get_json()
    if json is None:
        abort(400)
    logger.info("Event received")
    if json.get('object_kind') == 'push':
        logger.info("Handling a PUSH event")
        send_debug_message("Handling a PUSH event")
        return handle_push(json)

    try:
        if json['user']['username'] == GITLAB_SELF_USERNAME:
            # To prevent infinite loops and race conditions, ignore events related
            # to actions that this bot did
            message = 'Ignoring webhook from myself'
            logger.info(message)
            send_debug_message(message)
            abort(make_response({"message": message}, 400))
    except KeyError as e:
        message = f"{e} parameter expected but not found"
        logger.info(message)
        abort(make_response({"message": message}, 400))

    if json.get('object_kind') != 'merge_request':
        message = "Event wasnt PUSH or MR"
        logger.info(message)
        send_debug_message(message)
        abort(make_response({"message": message}, 400))

    logger.info("Handling a MR event")
    send_debug_message("Handling a MR event")
    return handle_mr(json)


def handle_push(push: dict) -> str:
    prefix = 'refs/heads/'

    if not push['ref'].startswith(prefix):
        logger.info(f'Unknown ref name {push["ref"]}')
        return ''

    project_name = push["repository"]["name"]
    branch_name = push['ref'][len(prefix):]
    logger.info(f'Handling push from {project_name}, branch {branch_name}')
    if project_name not in config()['projects']:
        message = f"The project `{project_name}` tried to use gorrabot's webhook, but its not in the configuration"
        send_message_to_error_channel(
            text=message,
            project_id=None,
            force_send=True
        )
        logger.info(message)
        return flask.abort(400, "project not in the configuration")

    branch_regex = regex_dict[project_name]

    if not re.match(branch_regex, branch_name):
        regex_branch_exceptions = config()['projects'][project_name].get('regex_branch_exceptions', [])
        if not re.match(r"^((dev|master|staging)|(.*/(dev|master|staging)))$", branch_name) \
                and branch_name not in regex_branch_exceptions:
            logger.warning("Branch does not match with regex")
            send_debug_message("Branch does not match with regex")
            send_message_to_error_channel(f"Unexpected push to `{project_name}`, branch `{branch_name}` do not follow "
                                          "expected regex format",
                                          project_id=config()['projects'][project_name]['id'])
        else:
            logger.info("dev, master or staging branch")
            send_debug_message("dev, master or staging branch")
    elif 'y2k' in str(get_push_info(push, branch_name)['issue_iid']):
        message = f'Ignoring push from branch {branch_name} because is y2k'
        send_message_to_error_channel(
            text=message,
            project_id=None,
            force_send=True
        )
        logger.info(message)
        return message
    else:
        check_required_attributes(push, branch_name)
        if 'multi-branch' in config()['projects'][project_name]:
            return handle_multi_main_push(push, prefix)

    return 'OK'


def handle_mr(mr_json: dict) -> str:
    if has_label(mr_json, GitlabLabels.DONT_TRACK):
        logger.warning('Ignoring because of label flag')
        send_debug_message('Ignoring because of label flag')
        return 'Ignoring all!'

    mr_attributes = mr_json['object_attributes']
    project_name = mr_json["repository"]["name"]
    source_branch = mr_attributes.get("source_branch")

    if project_name not in config()['projects']:
        logger.warning('Project not in the configuration')
        send_debug_message('Project not in the configuration')
        send_message_to_error_channel(
            text=f"The project `{project_name}` tried to use gorrabot's webhook, but its not in the configuration",
            project_id=None,
            force_send=True
        )
        return flask.abort(400, "Project not in the configuration")

    username = get_username(mr_json)
    (project_id, iid) = (mr_attributes['source_project_id'], mr_attributes['iid'])

    branch_regex = regex_dict[project_name]
    regex_branch_exceptions = config()['projects'][project_name].get('regex_branch_exceptions', [])
    logger.info(f"Handling MR #{iid} from branch {source_branch} of project {project_name}")
    if 'y2k' in str(iid):
        message = f'Ignoring MR from branch {source_branch} because is y2k'
        send_message_to_error_channel(
            text=message,
            project_id=None,
            force_send=True
        )
        logger.info(message)
        return message
    if not re.match(branch_regex, source_branch) \
       and source_branch not in regex_branch_exceptions:
        logger.info(f"Branch {source_branch} of repository {project_name} do not match regex")
        send_debug_message(f"Branch {source_branch} of repository {project_name} do not match regex")
        multi_brach = config()['projects'][project_name].get('multi-branch', '')
        msg_bad_branch_name = MSG_BAD_BRANCH_NAME.format(main_branches=multi_brach)
        comment_mr(project_id, iid, f"@{username}: {msg_bad_branch_name}", can_be_duplicated=False)

    is_multi_main = is_multi_main_mr(mr_json)

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
            has_label(mr_json, GitlabLabels.NO_CHANGELOG) or has_flag(project_name, "NO_CHANGELOG")
    ):
        message = 'Ignoring MR Changelog'
        logger.info(message)
        send_debug_message(message)
        return message
    mr_attributes = mr_json['object_attributes']
    (project_id, iid) = (mr_attributes['source_project_id'], mr_attributes['iid'])
    username = get_username(mr_json)

    changelog_filetype = config()['projects'][project_name]['changelog_filetype'] \
                         if 'changelog_filetype' in config()['projects'][project_name] else '.md'

    if not has_changed_changelog(project_id, iid, project_name, only_md=True):
        if has_changed_changelog(project_id, iid, project_name, only_md=False):
            logger.info(f"Not a valid changelog file type: {changelog_filetype}")
            msg = NO_VALID_CHANGELOG_FILETYPE.format(changelog_filetype=changelog_filetype)
        else:
            msg = MSG_MISSING_CHANGELOG
        comment_mr(project_id, iid, f"@{username}: {msg}")
        set_wip(project_id, iid)
        mr_attributes['work_in_progress'] = True


def get_iteration(push: dict, branch_name: str) -> dict:
    """ Gets an iteration from a given issue """

    push_info = get_push_info(push, branch_name)

    project_id = push_info['project_id']
    issue_iid = push_info['issue_iid']

    url = f'{GITLAB_API_PREFIX}/projects/{project_id}/issues/{issue_iid}/resource_iteration_events'
    iteration_info = paginated_get(url)

    # In order to get the last-used iteration, the list is reversed.
    iteration_info.reverse()

    # NOTE: first element is selected because of GitLab's list response format.
    iteration = iteration_info[0].get('iteration') \
                if iteration_info else None

    return iteration


def check_required_attributes(push: dict, branch_name: str) -> NoReturn:
    """
        Verifies if labels, weight, milestone and iteration exist in
        GitLab's PR response.
    """

    push_info = get_push_info(push, branch_name)
    project_id = push_info['project_id']
    project_name = push_info['project_name']
    issue_iid = push_info['issue_iid']
    issue = get_issue(project_id, issue_iid)
    messages = []

    labels: List[str] = issue['labels']
    if (
            all([not label.startswith("priority::") for label in labels]) and not
            (
                has_flag(project_name, "NO_PRIORITY")
            )
    ):
        logger.info("No priority label found")
        messages.append(MSG_WITHOUT_PRIORITY)
    if (
            all([not label.startswith("severity::") for label in labels]) and not
            (
                has_flag(project_name, "NO_SEVERITY")
            )
    ):
        logger.info("No severity label found")
        messages.append(MSG_WITHOUT_SEVERITY)
    weight = issue['weight']
    if weight is None:
        logger.info("Weight found")
        messages.append(MSG_WITHOUT_WEIGHT)
    milestone = issue['milestone']
    if milestone is None:
        logger.info("Milestone not found")
        messages.append(MSG_WITHOUT_MILESTONE)
    else:
        if milestone['title'] in BACKLOG_MILESTONE:
            logger.info("Backlog detected as milestone")
            messages.append(MSG_BACKLOG_MILESTONE)

    iteration = get_iteration(push, branch_name)
    if iteration is None:
        logger.info("Iteration not found")
        messages.append(MSG_WITHOUT_ITERATION)

    if len(messages) > 0:
        error_message_list = '\n    * '.join([''] + messages)
        username = push["user_username"]
        if username in gitlab_to_slack_user_dict:
            error_message = MSG_NOTIFICATION_PREFIX_WITH_USER.format(
                user=gitlab_to_slack_user_dict[username],
                branch=branch_name,
                project_name=project_name
            )
        else:
            error_message = MSG_NOTIFICATION_PREFIX_WITHOUT_USER.format(user=username,
                                                                        branch=branch_name,
                                                                        project_name=project_name
                                                                        )

        error_message = f"{error_message}{error_message_list}"
        send_message_to_error_channel(error_message, project_id=config()['projects'][project_name]['id'])


# @ehorvat: I believe this should be in a utils as it depends on gitlab
def has_changed_changelog(project_id: int, iid: int, project_name, only_md: bool):
    changes = get_mr_changes(project_id, iid)
    changed_files = get_changed_files(changes)
    for filename in changed_files:
        if filename.startswith('CHANGELOG'):
            valid_ext = config()['projects'][project_name]['changelog_filetype'] \
                        if 'changelog_filetype' in config()['projects'][project_name] \
                        else '.md'
            if not only_md or filename.endswith(valid_ext):
                return True
            else:
                if 'changelog_exceptions' in config()['projects'][project_name]:
                    _, file_name = os.path.split(filename)
                    if file_name in config()['projects'][project_name]['changelog_exceptions']:
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
    return 'multi-branch' in config()['projects'][mr_json["repository"]["name"]]


def main():
    gorrabot_timer = GorrabotTimer(config.cache_clear, 1800)  # execute every 30 minutes
    app.run(debug=True, use_reloader=True)


if __name__ == '__main__':
    main()
