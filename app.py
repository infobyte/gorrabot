import requests
from flask import Flask, request, abort
app = Flask(__name__)

TOKEN = '***REMOVED***'
API_PREFIX = 'https://gitlab.com/api/v4'

MSG_MISSING_CHANGELOG = 'Acá falta el changelog!!!'

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

    print("Processing MR #", mr['iid'])
    (project_id, iid) = (mr['source_project_id'], mr['iid'])
    if not has_changed_changelog(project_id, iid):
        username = get_username(json)
        set_wip(project_id, iid)
        comment_mr(project_id, iid, "@{}: {}".format(
            username, MSG_MISSING_CHANGELOG))

    return 'OK'


def get_username(data):
    if 'assignee' in data:
        return data['assignee']['username']
    return data['user']['username']


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


def comment_mr(project_id, iid, body):
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

