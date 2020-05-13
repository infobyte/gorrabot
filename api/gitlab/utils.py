import datetime


def parse_api_date(date):
    assert date.endswith('Z')
    return datetime.datetime.fromisoformat(date[:-1])
