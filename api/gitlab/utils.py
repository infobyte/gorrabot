import datetime
import re


def parse_api_date(date):
    assert date.endswith('Z')
    return datetime.datetime.fromisoformat(date[:-1])


def get_waiting_users_from_issue(issue):
    description = issue["description"]
    desc_lines = [line.strip() for line in description.splitlines()]
    match = list(filter(lambda line: re.match(r"WFD: .+", line), desc_lines))
    users = []
    if len(match) > 0:
        users = [user.strip() for user in match[0][4:].split(",")]

    return users
