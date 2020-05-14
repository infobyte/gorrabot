from requests import Session


def get_slack_user_data(session: Session):
    res = session.get("https://slack.com/api/users.list")
    res.raise_for_status()
    data = res.json()
    assert data["ok"]
    return data
