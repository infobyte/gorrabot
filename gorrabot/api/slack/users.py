from gorrabot.api.slack import slack_session, SLACK_API_PREFIX


def get_slack_user_data():
    res = slack_session.get(f"{SLACK_API_PREFIX}/users.list")
    res.raise_for_status()
    data = res.json()
    assert data["ok"]
    return data
