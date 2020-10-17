from logging import getLogger, INFO
from typing import List, NoReturn
import re

from gorrabot.api.gitlab import GitlabLabels
from gorrabot.api.gitlab.issues import get_issue, update_issue
from gorrabot.api.gitlab.merge_requests import (
    get_merge_requests,
    comment_mr,
    create_mr,
    get_related_merge_requests,
    get_mr
)
from gorrabot.api.gitlab.usernames import get_username
from gorrabot.api.slack.messages import send_debug_message
from gorrabot.config import config
from gorrabot.constants import MSG_NEW_MR_CREATED, MSG_CHECK_SUPERIOR_MR, regex_dict
from gorrabot.utils import get_related_issue_iid, fill_fields_based_on_issue, has_label


logger = getLogger()


def get_previous_or_next(project_name: str, branch_name: str, previous: bool) -> List[str]:
    """
    This will get the branch (e.g. tkt_***REMOVED***_XXXX_extra), and check if the previous branches MR exists
    (e.g. tkt_***REMOVED***_XXXX_extra; not tkt_***REMOVED***_XXXX_extra)
    """
    parent_branches: List[str] = config[project_name]['multi-branch']
    main_branch = re.match(regex_dict[project_name], branch_name).group('base')
    if previous:
        others_parent_main_branches = parent_branches[:parent_branches.index(main_branch)]
    else:
        others_parent_main_branches = parent_branches[parent_branches.index(main_branch) + 1:]
    send_debug_message(f"{others_parent_main_branches}")
    return [
        branch_name.replace(main_branch, others_parent_main_branch)  # "tkt_***REMOVED***_XXXX_extra".replace('***REMOVED***','***REMOVED***')
        for others_parent_main_branch in others_parent_main_branches
    ]


def get_previous(project_name: str, branch_name: str):
    return get_previous_or_next(project_name, branch_name, True)


def get_next(project_name: str, branch_name: str):
    return get_previous_or_next(project_name, branch_name, False)


def handle_multi_main_push(push: dict, prefix: str) -> str:
    logger.info("Handling multi main branch push")
    send_debug_message("Handling multi main branch push")
    project_name = push["repository"]["name"]
    branch_name = push['ref'][len(prefix):]

    previous_branches = get_previous(project_name, branch_name)

    if push['checkout_sha'] is not None:
        # Deleting a branch triggers a push event, and I don't want
        # that to create a new MR. So check that the branch wasn't
        # deleted by checking the checkout_sha.
        # See https://gitlab.com/gitlab-org/gitlab-ce/issues/54216
        return ensure_upper_version_is_created(
            push,
            branch_name,
            previous_branches
        )

    return "OK"


def ensure_upper_version_is_created(push: dict, branch_name: str, previous_branches: List[str]) -> str:
    """If there exists a MR with a source branch that is in
    previous_branches and there is no MR whose source branch is
    branch_name, create a new MR inheriting from the parent MR.

    Exclude all closed MRs from this logic.
    """
    logger.info(f"Checking if other main branch/MR exists of {branch_name}")
    send_debug_message(f"Checking if other main branch/MR exists of {branch_name}")
    project_name = push["repository"]["name"]
    project_id = push['project_id']
    mrs_for_this_branch = get_merge_requests(
        project_id,
        {'source_branch': branch_name}
    )
    if any(mr['state'] != 'closed' for mr in mrs_for_this_branch):
        logger.info(f"All MR are closed")
        send_debug_message(f"All MR are closed")
        return "OK, All MR are closed"

    previous_mr = None
    for previous_branch_name in previous_branches:
        merge_requests = get_merge_requests(
            project_id,
            {'source_branch': previous_branch_name}
        )
        merge_requests = [
            mr for mr in merge_requests
            if mr['state'] != 'closed'
        ]
        if len(merge_requests) == 1:
            # If the length is greater than 1, I don't know which branch should
            # I use.
            previous_mr = merge_requests[0]
            break
        else:
            send_debug_message(f"{merge_requests}")

    if previous_mr is None:
        logger.info(f"Cant find 1 MR (could be more), {previous_branches}")
        send_debug_message(f"Cant find 1 MR (could be more), {previous_branches}")
        return f"Cant find 1 MR (could be more), {previous_branches}"


    mr_data = create_similar_mr(previous_mr, project_name, branch_name)
    new_mr = create_mr(previous_mr['source_project_id'], mr_data)
    fill_fields_based_on_issue(new_mr)
    username = get_username(previous_mr)
    return comment_mr(
        project_id,
        new_mr['iid'],
        f'@{username}: {MSG_NEW_MR_CREATED}'
    )


def create_similar_mr(parent_mr: dict, project_name: str, branch_name: str) -> dict:
    main_branch = re.match(regex_dict[project_name], branch_name).group('base')
    target_branch = f"{main_branch}/dev"
    new_title = (
        f"{parent_mr['title']} ({main_branch} edition)"
    )
    # if not new_title.startswith('WIP: '):
    #     new_title = 'WIP: ' + new_title
    new_description = (
        f"""
{parent_mr['description']}

Created with <3 by @gorrabot, based on merge request
!{parent_mr['iid']}
        """
    )

    new_labels = set(parent_mr['labels'])
    new_labels.add(GitlabLabels.NO_CHANGELOG)
    new_labels = list(new_labels)

    mr = {
        'source_branch': branch_name,
        'target_branch': target_branch,
        'title': new_title,
        'description': new_description,
        'labels': new_labels
    }
    return mr


def notify_unmerged_superior_mrs(mr_json: dict):
    """Warn the user who merged mr if there also are ***REMOVED*** or ***REMOVED*** merge
    requests for the same issue."""
    mr = mr_json["object_attributes"]
    assert mr['state'] == 'merged'
    issue_iid = get_related_issue_iid(mr_json)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return

    related_mrs = get_related_merge_requests(project_id, issue_iid)
    related_mrs = [rmr for rmr in related_mrs
                   if rmr['state'] not in ('merged', 'closed')]

    expected_next_branches = get_next(project_id, mr['source_branch'])

    # Discard MRs that are not of expected_next_branches
    related_mrs = [
        rmr for rmr in related_mrs
        if rmr['source_branch'] in expected_next_branches
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


def add_multiple_merge_requests_label_if_needed(mr_json: dict):
    mr = mr_json["object_attributes"]
    issue_iid = get_related_issue_iid(mr_json)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    if mr['state'] == 'closed':
        # Not adding this could mail the assertion below fail
        return

    related_mrs = get_related_merge_requests(mr['source_project_id'], issue_iid)

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
        if issue is None or has_label(mr_json, GitlabLabels.MULTIPLE_MR):
            return
        new_labels = issue['labels']
        new_labels.append(GitlabLabels.MULTIPLE_MR)
        new_labels = list(set(new_labels))
        data = {"labels": ','.join(new_labels)}
        return update_issue(project_id, issue_iid, data)
