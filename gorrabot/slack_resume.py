#!/usr/bin/env python
import datetime
import os
import sys
from collections import defaultdict
import logging
import time
from gorrabot.api.constants import gitlab_to_slack_user, MAX_ISSUES_ACCEPTED
from gorrabot.api.gitlab.issues import get_accepted_issues
from gorrabot.api.gitlab.usernames import get_usernames_from_mr_or_issue
from gorrabot.api.slack.messages import send_message_to_user, check_can_send_slack_messages
from gorrabot.api.slack.users import get_slack_user_data
from gorrabot.constants import OLD_MEMBERS
from gorrabot.utils import get_decision_issues, get_waiting_users_from_issue, get_staled_merge_requests, create_report,\
    clear_cached_functions
from gorrabot.config import config

DRY_RUN = os.environ.get("DRY_RUN", None)

REPORT_USERS = config()['gitlab'].get('REPORT_USERS', [])

project_ids = [int(config()['projects'][project_name]['id']) for project_name in config()['projects']]

"""
The idea of this script is identify who is blocking other dev and notify about this:

The way to set that someone decision is blocking another dev is by set the "On decision" label, 
and put in the description whose decision is necessary by this meta-info:

WFD: [comma-separated-slack_user/gitlab-user]

"""

STALE_WIP = "stale_wip"
STALE_NO_WIP = "stale_no_wip"
WAITING_DECISION = "waiting-decision"
ACCEPTED_ISSUES = "accepted-issues"



def get_waiting_users(issue):
    users = [gitlab_to_slack_user(user[1:])
             if user[0] == "@" else user for user in get_waiting_users_from_issue(issue) if len(user) > 0
            ]
    return users


def get_slack_user_from_mr_or_issue(elem: dict):
    return [gitlab_to_slack_user(user) for user in get_usernames_from_mr_or_issue(elem)]


def get_staled_wip_merge_requests(project_id: int):
    return get_staled_merge_requests(project_id, 'yes')


def get_staled_no_wip_merge_requests(project_id: int):
    return get_staled_merge_requests(project_id, 'no')


def send_report_to_user(username, notify_dict, slack_user_data):
    text = "H0L4! Este es tu reporte que te da tu amigo, gorrabot :gorrabot2:!\n"
    send_message_to_user(username, text, slack_user_data)
    for user in notify_dict:
        time.sleep(1)
        report = create_report(notify_dict, user)
        send_message_to_user(username, report, slack_user_data)


def gather_data(notify_dict:dict, project_id:str, user):
    can_send_message = check_can_send_slack_messages(project_id)

    if not can_send_message:
        # project cannot send messages to Slack
        return

    checking_functions = [
        {"elem_picker": get_staled_wip_merge_requests, "user_picker": get_slack_user_from_mr_or_issue,
         "key": STALE_WIP},
        {"elem_picker": get_staled_no_wip_merge_requests, "user_picker": get_slack_user_from_mr_or_issue,
         "key": STALE_NO_WIP},
        {"elem_picker": get_decision_issues, "user_picker": get_waiting_users, "key": WAITING_DECISION},
        {"elem_picker": get_accepted_issues, "user_picker": get_slack_user_from_mr_or_issue, "key": ACCEPTED_ISSUES}
    ]

    for function_dict in checking_functions:
        for elem in function_dict["elem_picker"](project_id):
            if user is not None:
                notify_dict[username][function_dict["key"]].append(elem)
            else:
                usernames = function_dict["user_picker"](elem)

                for username in usernames:
                    if username not in OLD_MEMBERS:
                        notify_dict[username][function_dict["key"]].append(elem)


def main(user=None, project=None):
    notify_dict = defaultdict(lambda: {STALE_WIP: [], STALE_NO_WIP: [], WAITING_DECISION: [], ACCEPTED_ISSUES: []})
    slack_user_data = get_slack_user_data()
    if project is not None:
        gather_data(notify_dict, project, user)
    else:
        for project_id in project_ids:
            gather_data(notify_dict, project_id, user)

    for username in notify_dict:
        if username is None:
            continue
        text = "H0L4! Este es tu reporte que te da tu amigo, gorrabot :gorrabot2:!\n"
        send = False
        if len(notify_dict[username][STALE_WIP]) > 0:
            text += ":warning: Algunos de tus MR con WIP/Draft estan " \
                    "estancados, estos son!:\n"
            text = "+ ".join([text] + [url['web_url'] + "\n" for url in notify_dict[username][STALE_WIP]])
            send = True
        else:
            text += "No tenes MR en WIP/Draft estancados :ditto:!\n"
        if len(notify_dict[username][STALE_NO_WIP]) > 0:
            text += ":warning: Algunos de tus MR sin WIP/Draft estan estancados, si creés que alguno tiene todo lo necesario " \
                    "para ser revisado, pedí approves. También fijate si se puede aclarar mejor qué se " \
                    "hizo y por qué, para hacerle la tarea más fácil a quien haga review de esto:\n"
            text = "+ ".join([text] + [url['web_url'] + "\n" for url in notify_dict[username][STALE_NO_WIP]])
            send = True
        else:
            text += "No tenes MR sin WIP/Draft estancados :ditto:!\n"
        if len(notify_dict[username][ACCEPTED_ISSUES]) > MAX_ISSUES_ACCEPTED:
            text += f":x: Tenes mas de {MAX_ISSUES_ACCEPTED} issues en 'Accepted', fijate:\n"
            text = "+ ".join([text] + [url['web_url'] + "\n" for url in notify_dict[username][ACCEPTED_ISSUES]])
            send = True
        if len(notify_dict[username][WAITING_DECISION]) > 0:
            text += "Hay issues esperando por tu decision, por favor revisalos, esto bloquea al equipo dev:\n"
            text = "+ ".join([text] + [url['web_url'] + "\n" for url in notify_dict[username][WAITING_DECISION]])
            send = True
        text += "Nos vemos en el proximo reporte :ninja:"

        if send and DRY_RUN is None:
            send_message_to_user(username, text, slack_user_data)
    clear_cached_functions()
    for username in REPORT_USERS:
        send_report_to_user(username, notify_dict, slack_user_data)


if __name__ == '__main__':
    logger = logging.getLogger(__name__)
    logger.info("Starting Slack Resume")
    day_number = datetime.datetime.today().weekday()

    if day_number < 5 or DRY_RUN is not None:
        main()
    else:
        logger.info("It's weekend, so I watch series, I'm not going to talk in slack")
    logger.info("Stopping Slack Resume")
