
gitlab_to_slack_user_dict = {
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

slack_to_gitlab_user_dict = {value: key for key, value in gitlab_to_slack_user_dict.items()}


def gitlab_to_slack_user(user: str):
    return gitlab_to_slack_user_dict[user] if user in gitlab_to_slack_user_dict else None


def slack_to_gitlab_user(user: str):
    return slack_to_gitlab_user_dict[user] if user in slack_to_gitlab_user_dict else None


MAX_ISSUES_ACCEPTED = 2
