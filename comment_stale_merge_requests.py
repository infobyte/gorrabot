import sys

from app import (
    comment_mr,
    get_staled_wip_merge_requests,
    get_username,
    MSG_MR_OLD_MEMBER,
    MSG_STALE_MR,
    OLD_MEMBERS,
    stale_mr_message_interval,
    get_mr, #TODO remove
)

project_id = int(sys.argv[1])

staled = list(get_staled_wip_merge_requests(project_id))
print(f'Found {len(staled)} staled merge requests')
for mr in staled:
    username = get_username(mr)
    if username in OLD_MEMBERS:
        comment_mr(
            project_id,
            mr['iid'],
            f'{MSG_MR_OLD_MEMBER}',
            min_time_between_comments=stale_mr_message_interval
        )
    else:
        comment_mr(
            project_id,
            mr['iid'],
            f'@{username}: {MSG_STALE_MR}',
            min_time_between_comments=stale_mr_message_interval
        )
