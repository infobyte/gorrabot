from flask import make_response

from gorrabot.config import config
from gorrabot.slack_resume import main


def handle_summary(content):
    user = content.get('user_name')
    project = content.get('text').strip()
    message = ''
    if project != '':
        if any([accepted_project['id'] == project for accepted_project in config()['projects']]):
            message = "Project found"
            main(user, project)
        else:
            message = "Project not found, sending full report"
            main(user)
    message += 'Sending report'
    return make_response({"message": message}, 200)


def handle_branch(content):
    return make_response({"message": "Todavia no hecho"}, 200)
