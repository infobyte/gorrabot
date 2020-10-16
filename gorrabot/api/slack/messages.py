from gorrabot.api.slack import slack_session, SLACK_API_PREFIX


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


def send_message_to_channel(slack_channel: str, text: str):
    params = {
        "channel": slack_channel,
        "text": text
    }
    res = slack_session.post(f"{SLACK_API_PREFIX}/chat.postMessage", params=params)
    return res


def send_message_to_error_channel(text: str):
    send_message_to_channel("#***REMOVED***-notification", text)
