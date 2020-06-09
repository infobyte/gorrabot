from gorrabot.api.gitlab import GitlabLabels
from gorrabot.api.gitlab.issues import get_issue, update_issue
from gorrabot.api.gitlab.jobs import get_commit_jobs, retry_job
from gorrabot.api.gitlab.merge_requests import (
    get_merge_requests,
    comment_mr,
    create_mr,
    get_related_merge_requests,
    get_mr
)
from gorrabot.api.gitlab.usernames import get_username
from gorrabot.constants import MSG_NEW_MR_CREATED, MSG_CHECK_SUPERIOR_MR
from gorrabot.utils import get_related_issue_iid, get_branch_last_commit, fill_fields_based_on_issue, has_label


def handle_multi_main_push(push: dict, prefix: str):
    branch_name = push['ref'][len(prefix):]

    if '***REMOVED***' in branch_name:
        parent_branches = [
            branch_name.replace('***REMOVED***', '***REMOVED***')
        ]
    elif '***REMOVED***' in branch_name:
        # keep ***REMOVED*** first so ensure_upper_version_is_created
        # won't create a MR based on another MR automatically
        # created by gorrabot
        parent_branches = [
            branch_name.replace('***REMOVED***', '***REMOVED***'),
            branch_name.replace('***REMOVED***', '***REMOVED***'),
        ]
    else:
        parent_branches = []

    if push['checkout_sha'] is not None:
        # Deleting a branch triggers a push event, and I don't want
        # that to create a new MR. So check that the branch wasn't
        # deleted by checking the checkout_sha.
        # See https://gitlab.com/gitlab-org/gitlab-ce/issues/54216
        ensure_upper_version_is_created(
            push['project_id'],
            branch_name,
            parent_branches
        )

    return "OK"


def ensure_upper_version_is_created(project_id: int, branch_name: str, parent_branches):
    """If there exists a MR with a source branch that is in
    parent_branches and there is no MR whose source branch is
    branch_name, create a new MR inheriting from the parent MR.

    Exclude all closed MRs from this logic.
    """

    mrs_for_this_branch = get_merge_requests(
        project_id,
        {'source_branch': branch_name}
    )
    if any(mr['state'] != 'closed' for mr in mrs_for_this_branch):
        return

    parent_mr = None
    for parent_branch_name in parent_branches:
        merge_requests = get_merge_requests(
            project_id,
            {'source_branch': parent_branch_name}
        )
        merge_requests = [
            mr for mr in merge_requests
            if mr['state'] != 'closed'
        ]
        if len(merge_requests) == 1:
            # If the length is greater than 1, I don't know which branch should
            # I use.
            parent_mr = merge_requests[0]
            break

    if parent_mr is None:
        return

    mr_data = create_similar_mr(parent_mr, branch_name)
    new_mr = create_mr(parent_mr['source_project_id'], mr_data)
    fill_fields_based_on_issue(new_mr)
    username = get_username(parent_mr)
    comment_mr(
        project_id,
        new_mr['iid'],
        f'@{username}: {MSG_NEW_MR_CREATED}'
    )


to_main_branch = {
    '***REMOVED***': '***REMOVED***/dev',
    '***REMOVED***': '***REMOVED***/dev',
}


def create_similar_mr(parent_mr: dict, source_branch: str):
    matches = [version for version in to_main_branch.keys() if version in source_branch]
    assert len(matches) > 0
    target_branch = to_main_branch[matches[0]]
    new_title = (
        f"{parent_mr['title']} ({target_branch.replace('/dev','')} edition)"
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
        'source_branch': source_branch,
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
