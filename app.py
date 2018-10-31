import os
import requests
from flask import Flask, request, abort
app = Flask(__name__)

TOKEN = os.environ['GITLAB_TOKEN']
API_PREFIX = 'https://gitlab.com/api/v4'

MSG_MISSING_CHANGELOG = (
    'Si que te aprueben un merge request tu quieres, tocar el changelog tu '
    'debes'
)
MSG_TKT_MR = (
    'Tener merge requests con "Tkt ***REMOVED***" en el título no es muy útil ya que '
    'puedo ver esa información en el nombre del branch. Se podría usar un '
    'título más descriptivo para este merge request.'
)

session = requests.Session()
session.headers['Private-Token'] = TOKEN

@app.route('/webhook', methods=['POST'])
def homepage():
    json = request.get_json()
    if json is None:
        abort(400)
    # print('Arrived request', json)
    if json.get('object_kind') != 'merge_request':
        return 'I only process merge requests right now!'
    mr = json['object_attributes']

    if mr['work_in_progress']:
        return 'Ignoring WIP MR'
    if mr['state'] in ('merged', 'closed'):
        return 'Ignoring closed MR'

    if any(
            label['title'] == 'no-changelog'
            for label in json.get('labels', [])):
        return 'Ignoring MR with label no-changelog'

    print("Processing MR #", mr['iid'])
    (project_id, iid) = (mr['source_project_id'], mr['iid'])

    username = get_username(json)
    if not has_changed_changelog(project_id, iid):
        comment_mr(project_id, iid, "@{}: {}".format(
            username, MSG_MISSING_CHANGELOG))
        set_wip(project_id, iid)
    if mr['title'].lower().startswith('tkt '):
        comment_mr(project_id, iid, "@{}: {}".format(
            username, MSG_TKT_MR), can_be_duplicated=False)

    return 'OK'


def get_username(data):
    if 'assignee' in data:
        return data['assignee']['username']
    user_id = data['object_attributes']['author_id']
    res = session.get(API_PREFIX + '/users/{}'.format(user_id))
    res.raise_for_status()
    return res.json()['username']


def has_changed_changelog(project_id, iid):
    # changes = get_mr_changes(mr['source_project_id'], mr['iid'])  # TODO borrame
    changes = get_mr_changes(project_id, iid)
    changed_files = get_changed_files(changes)
    return any(
        filename.startswith('CHANGELOG') and filename.endswith('.md')
        for filename in changed_files
        )


def mr_url(project_id, iid):
    return '{}/projects/{}/merge_requests/{}'.format(
            API_PREFIX, project_id, iid)


def get_mr_changes(project_id, iid):
    url = mr_url(project_id, iid) + '/changes'
    res = session.get(url)
    res.raise_for_status()
    return res.json()['changes']


def get_changed_files(changes):
    return set(change['new_path'] for change in changes)


def comment_mr(project_id, iid, body, can_be_duplicated=True):
    if not can_be_duplicated:
        # Ugly hack to drop user mentions from body
        search_title = body.split(': ', 1)[-1]
        res = session.get(mr_url(project_id, iid) + '/notes')
        res.raise_for_status()
        comments = res.json()
        if any(search_title in comment['body']
                for comment in comments):
            # This comment has already been made
            return

    url = mr_url(project_id, iid) + '/notes'
    data = {"body": body}
    res = session.post(url, json=data)
    res.raise_for_status()
    return res.json()


def set_wip(project_id, iid):
    url = mr_url(project_id, iid)
    res = session.get(url)
    res.raise_for_status()
    mr = res.json()

    assert not mr['work_in_progress'] and not mr['title'].startswith('WIP:')
    data = {"title": "WIP: " + mr['title']}
    res = session.put(url, json=data)
    res.raise_for_status()
    return res.json()


if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)

