from requests import Session

from constants import MSG_NEW_MR_CREATED
from api.gitlab.mr import (
    get_merge_requests
)


def handle_multi_main_push(push, prefix):
    branch_name = push['ref'][len(prefix):]

    if '/dev' in branch_name:
        retry_conflict_check_of_mrs_with_target_branch(
            push['project_id'],
            branch_name
        )

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

    for parent_branch_name in parent_branches:
        retry_merge_conflict_check_of_branch(
            push['project_id'], parent_branch_name
        )

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


def ensure_upper_version_is_created(project_id, branch_name, parent_branches):
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


def create_similar_mr(parent_mr, source_branch):
    assert '***REMOVED***' in source_branch or '***REMOVED***' in source_branch
    if '***REMOVED***' in source_branch:
        target_branch = '***REMOVED***/dev'
    elif '***REMOVED***' in source_branch:
        target_branch = '***REMOVED***/dev'
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
    new_labels.add('no-changelog')
    new_labels = list(new_labels)

    mr = {
        'source_branch': source_branch,
        'target_branch': target_branch,
        'title': new_title,
        'description': new_description,
        'labels': new_labels
    }
    return mr


def retry_merge_conflict_check_of_branch(project_id, branch_name):
    last_commit = get_branch_last_commit(project_id, branch_name)
    if last_commit is None:
        return
    jobs = get_commit_jobs(project_id, last_commit['id'])
    try:
        mc_check_job = next(job for job in jobs
                            if job['name'] == 'merge_conflict_check')
    except StopIteration:
        return
    print(f'Retrying merge conflict check job for branch '
          f'{branch_name}')
    retry_job(project_id, mc_check_job['id'])


def retry_conflict_check_of_mrs_with_target_branch(session: Session, project_id: int, target_branch: str):
    """Find all MRs with the specified target branch, and in the current
    or upcoming milestones. Retry the merge conflict check job of all of
    them"""
    merge_requests = get_merge_requests(
        session,
        project_id,
        {'target_branch': target_branch, 'state': 'opened'}
    )

    # This will ignore merge requests of old milestones
    # merge_requests = filter_current_or_upcoming_mrs(merge_requests)

    for mr in merge_requests:
        retry_merge_conflict_check_of_branch(
            project_id,
            mr['source_branch']
        )
