from gorrabot.api.gitlab import gitlab_session, GITLAB_API_PREFIX


# TODO DEPRECATE TO MULTIPLE ASSIGNEES -> get_usernames_from_mr_or_issue
def get_username(data: dict):
    if data.get('assignee'):
        return data['assignee']['username']
    elif data.get('author'):
        return data['author']['username']

    user_id = data['object_attributes']['author_id']
    res = gitlab_session.get(GITLAB_API_PREFIX + f'/users/{user_id}')
    res.raise_for_status()
    return res.json()['username']


def get_usernames_from_mr_or_issue(data: dict):
    if len(data.get('assignees')):
        return [assignee['username'] for assignee in data['assignees']]
    elif data.get('author'):
        return [data['author']['username']]

    user_id = data['object_attributes']['author_id']
    res = gitlab_session.get(GITLAB_API_PREFIX + f'/users/{user_id}')
    res.raise_for_status()
    return [res.json()['username']]
