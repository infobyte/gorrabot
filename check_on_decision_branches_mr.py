import os
import re
import requests
import sys
import json
from collections import defaultdict

from app import (
    OLD_MEMBERS,
    get_staled_wip_merge_requests,
    get_decision_issues,
    get_usernames_from_mr_or_issue,
    get_accepted_issues
)

BOT_TOKEN = os.environ['SLACK_BOT_TOKEN']
REPORT_USERS = ["***REMOVED***"]

project_ids = [int(i) for i in sys.argv[1].split(',')]

slack_session = requests.Session()
slack_session.params["token"] = BOT_TOKEN

"""
The idea of this script is identify who is blocking other dev and notify about this:

The way to set that someone decision is blocking another dev is by set the "On decision" label, 
and put in the description whose decision is necessary by this meta-info:

WFD: [comma-separated-slack_user/gitlab-user]

"""

gitlab_to_slack_user = {
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***",
    "***REMOVED***": "***REMOVED***"
}

STALE_MR = "stale_mr"
WAITING_DECISION = "waiting-decision"
ACCEPTED_ISSUES = "accepted-issues"

notify_dict = defaultdict(lambda: {STALE_MR: [], WAITING_DECISION: [], ACCEPTED_ISSUES: []})

MAX_ACCEPTED = 2


def to_slack_user(user: str):
    return gitlab_to_slack_user[user]


def get_waiting_users(issue):
    description = issue["description"]
    desc_lines = [line.strip() for line in description.splitlines()]
    match = list(filter(lambda line: re.match(r"WFD: .+", line), desc_lines))
    users = []
    if len(match) > 0:
        users = [user.strip() for user in match[0][4:].split(",")]
        users = [to_slack_user(user[1:]) if user[0] == "@" else user for user in users if len(user) > 0]

    return users


res = slack_session.get("https://slack.com/api/users.list")

res.raise_for_status()
data = res.json()
assert data["ok"]
slack_users_data = {elem["name"]: elem for elem in data["members"] if not elem['deleted'] and not elem["is_bot"]}


def send_message(slack_user: str, text: str):
    if slack_user not in slack_users_data:
        print(f"Ask for send message to user: {slack_user}, who is not in the slack api response")
        return None
    else:
        params = {
            "channel" : slack_users_data[slack_user]['id'],
            "text": text,
            "as_user": True
        }
        res = slack_session.post("https://slack.com/api/chat.postMessage", params=params)
        return res


def get_slack_user_from_mr_or_issue(elem):
    return [to_slack_user(user) for user in get_usernames_from_mr_or_issue(elem)]


for project_id in project_ids:

    checking_functions = [
        {"elem_picker": get_staled_wip_merge_requests, "user_picker": get_slack_user_from_mr_or_issue, "key": STALE_MR},
        {"elem_picker": get_decision_issues, "user_picker": get_waiting_users, "key": WAITING_DECISION},
        {"elem_picker": get_accepted_issues, "user_picker": get_slack_user_from_mr_or_issue, "key": ACCEPTED_ISSUES}
    ]

    for function_dict in checking_functions:
        for elem in function_dict["elem_picker"](project_id):
            usernames = function_dict["user_picker"](elem)

            for username in usernames:
                if username not in OLD_MEMBERS:
                    notify_dict[username][function_dict["key"]].append(elem['web_url'])
                else:
                    # ?
                    pass


for username in notify_dict:
    text = "H0L4! Este es tu reporte que te da tu amigo, gorrabot :gorrabot2:!\n"
    send = False
    if len(notify_dict[username][STALE_MR]) > 0:
        text += ":warning: Algunos de tus MR estan estancados, estos son!:\n"
        text = "+ ".join([text] + [url + "\n" for url in notify_dict[username][STALE_MR]])
        send = True
    else:
        text += "No tenes MR estancados :ditto:!\n"
    if len(notify_dict[username][ACCEPTED_ISSUES]) > MAX_ACCEPTED:
        text += f":x: Tenes mas de {MAX_ACCEPTED} issues en 'Accepted', fijate:\n"
        text = "+ ".join([text] + [url + "\n" for url in notify_dict[username][ACCEPTED_ISSUES]])
        send = True
    if len(notify_dict[username][WAITING_DECISION]) > 0:
        text += "Hay issues esperando por tu decision, por favor revisalos, esto bloquea al equipo dev:\n"
        text = "+ ".join([text] + [url + "\n" for url in notify_dict[username][WAITING_DECISION]])
        send = True
    if username in REPORT_USERS:
        report = json.dumps({
            report_user: {
                key: len(notify_dict[report_user][key])
                for key in notify_dict[report_user]
            } for report_user in notify_dict
        }, indent=4)
        text += f"Te mando el resumen en un json: ```{report}```\n"

    text += "Nos vemos en el proximo reporte :ninja:"

    if send and username in REPORT_USERS:
        send_message(username, text)
