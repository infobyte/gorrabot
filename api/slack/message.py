from api.slack import slack_session, SLACK_API_PREFIX


def send_message(slack_user: str, text: str, slack_users_data: dict):
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
