import datetime


def parse_api_date(date):  # TODO I DO NOT LIKE THIS HERE
    assert date.endswith('Z')
    return datetime.datetime.fromisoformat(date[:-1])
