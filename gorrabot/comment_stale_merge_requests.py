#!/usr/bin/env python
import sys

from gorrabot.api.gitlab.merge_requests import comment_mr
from gorrabot.api.gitlab.usernames import get_username
from gorrabot.constants import OLD_MEMBERS, MSG_MR_OLD_MEMBER, stale_mr_message_interval, MSG_STALE_MR
from gorrabot.utils import get_staled_merge_requests
from gorrabot.config import config

""""(
    comment_mr,
    get_staled_merge_requests,
    get_username,
    MSG_MR_OLD_MEMBER,
    MSG_STALE_MR,
    OLD_MEMBERS,
    stale_mr_message_interval,
)"""
project_ids = [int(config()['projects'][project_name]['id']) for project_name in config()['projects']]


def main():
    for project_id in project_ids:
        staled = list(get_staled_merge_requests(project_id, wip='yes'))
        print(f'Found {len(staled)} staled merge requests in project: {project_id}')
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


if __name__ == '__main__':
    main()
