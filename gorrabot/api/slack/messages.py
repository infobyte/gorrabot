import os

from gorrabot.api.gitlab.projects import get_project_name
from gorrabot.api.slack import slack_session, SLACK_API_PREFIX
from gorrabot.config import config


def check_can_send_slack_messages(project_id: int):
    """ Checks the send_message_to_slack config param is set """

    project_name = get_project_name(project_id)

    send_message_to_slack = False
    if project_name in config['projects']:
        send_message_to_slack = config['projects'][project_name].get('send_message_to_slack', False)

    return send_message_to_slack


def send_message_to_user(slack_user: str, text: str, slack_users_data: dict):
    slack_users_data = {
        elem["name"]: elem for elem in slack_users_data["members"] if not elem['deleted'] and not elem["is_bot"]
    }

    if slack_user not in slack_users_data:
        print(f"Ask for send message to user: {slack_user}, who is not in the slack api response")
        return None
    else:
        params = {
            "channel": slack_users_data[slack_user]['id'],
            "text": text,
            "as_user": True
        }
        res = slack_session.post(f"{SLACK_API_PREFIX}/chat.postMessage", params=params)
        return res


def send_message_to_channel(slack_channel: str, text: str, project_id: int):

    can_send_message = check_can_send_slack_messages(project_id)

    if not can_send_message:
        # project cannot send message to Slack
        return

    params = {
        "channel": slack_channel,
        "text": text,
        "link_names": True
    }
    res = slack_session.post(f"{SLACK_API_PREFIX}/chat.postMessage", params=params)
    return res


def send_message_to_error_channel(text: str, project_id: int):
    send_message_to_channel("#***REMOVED***-notification", text, project_id)


def send_debug_message(text: str, project_id: int):
    if 'DEBUG' in os.environ:
        send_message_to_channel("***REMOVED***", text, project_id)  # ***REMOVED*** ID
