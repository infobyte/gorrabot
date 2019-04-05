import os
import re
import requests
from flask import Flask, request, abort
app = Flask(__name__)

TOKEN = os.environ['GITLAB_TOKEN']
REQUEST_TOKEN = os.environ['GITLAB_CHECK_TOKEN']
SELF_USERNAME = os.environ['GITLAB_BOT_USERNAME']

API_PREFIX = 'https://gitlab.com/api/v4'

MSG_MISSING_CHANGELOG = (
    'Si que te aprueben un merge request tu quieres, tocar el changelog tu '
    'debes'
)
NO_MD_CHANGELOG = (
    'El fichero que se creó en el directorio `CHANGELOG` no tiene extensión '
    '`.md` por lo que no va a ser tomado en cuenta por el sistema de '
    'generación de changelogs. Hay que arreglar esto para que se pueda '
    'mergear el MR.'
)
MSG_TKT_MR = (
    'Tener merge requests con "Tkt ***REMOVED***" en el título no es muy útil ya que '
    'puedo ver esa información en el nombre del branch. Se podría usar un '
    'título más descriptivo para este merge request.'
)
MSG_BAD_BRANCH_NAME = (
    'Los nombres de branch deben tener el formato tkt_***REMOVED***_1234_short_desc. '
    'Es decir, tienen que tener la versión para la que se quieren mergear '
    '(***REMOVED***, ***REMOVED*** o ***REMOVED***), el número de ticket y una descripción corta.'
    '\n\n'
    'En caso de que sea un ticket de soporte usar el prefijo sup en vez de '
    'tkt. Si se trata de un branch experimental que no va a ser mergeado a '
    'corto plazo se puede usar el prefijo exp en vez de tkt.'
    '\n\n'
    'Esta te la dejo pasar, la próxima recordá usar esta nomenclatura!'
)

branch_regex = r'***REMOVED***'

session = requests.Session()
session.headers['Private-Token'] = TOKEN


@app.route('/webhook', methods=['POST'])
def homepage():
    if request.headers.get('X-Gitlab-Token') != REQUEST_TOKEN:
        abort(403)
    json = request.get_json()
    if json is None:
        abort(400)

    if json['user']['username'] == SELF_USERNAME:
        # To prevent infinite loops and race conditions, ignore events related
        # to actions that this bot did
        return 'Ignoring webhook from myself'

    if json.get('object_kind') != 'merge_request':
        return 'I only process merge requests right now!'

    if has_label(json, 'sacate-la-gorra'):
        return 'Ignoring all!'

    mr = json['object_attributes']
    username = get_username(json)
    (project_id, iid) = (mr['source_project_id'], mr['iid'])

    check_issue_reference_in_description(mr)
    add_multiple_merge_requests_label_if_needed(mr)
    sync_related_issue(mr)
    fill_fields_based_on_issue(mr)

    if not re.match(branch_regex, mr['source_branch']):
        comment_mr(project_id, iid, "@{}: {}".format(
            username, MSG_BAD_BRANCH_NAME), can_be_duplicated=False)

    if mr['work_in_progress']:
        return 'Ignoring WIP MR'
    if mr['state'] in ('merged', 'closed'):
        return 'Ignoring closed MR'

    if has_label(json, 'no-changelog'):
        return 'Ignoring MR with label no-changelog'

    print("Processing MR #", mr['iid'])

    if not has_changed_changelog(project_id, iid, only_md=True):
        if has_changed_changelog(project_id, iid, only_md=False):
            msg = NO_MD_CHANGELOG
        else:
            msg = MSG_MISSING_CHANGELOG
        comment_mr(project_id, iid, "@{}: {}".format(
            username, msg))
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


def has_label(obj, label_name):
    return any(label['title'] == label_name
               for label in obj.get('labels', []))


def has_changed_changelog(project_id, iid, only_md):
    changes = get_mr_changes(project_id, iid)
    changed_files = get_changed_files(changes)
    for filename in changed_files:
        if filename.startswith('CHANGELOG'):
            if not only_md or filename.endswith('.md'):
                return True
    return False


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
    return update_mr(project_id, iid, data)


def update_mr(project_id, iid, data):
    url = mr_url(project_id, iid)
    res = session.put(url, json=data)
    res.raise_for_status()
    return res.json()


def sync_related_issue(mr):
    """Change the status of the issue related to the new/updated MR

    Get the issue by matching the source branch name. If the issue has
    the multiple-merge-requests label, do nothing.

    WIP MR -> Label issue as accepted
    Pending merge/approbal MR -> Label issue as test
    Merged MR -> Close issue and delete status labels (accepted, test)
    # Closed MR -> Close issue, delete status label and label as invalid
    # Closed MR -> Do nothing, assume that another MR will be created
    Closed MR -> Delete status labels (set to new)
    """

    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    issue = get_issue(project_id, issue_iid)
    if issue is None or has_label(mr, 'multiple-merge-requests'):
        return

    close = False
    new_labels = issue['labels']
    try:
        new_labels.remove('Test')
    except ValueError:
        pass
    try:
        new_labels.remove('Accepted')
    except ValueError:
        pass

    if mr['work_in_progress']:
        new_labels.append('Accepted')
    elif mr['state'] == 'opened' and not mr['work_in_progress']:
        new_labels.append('Test')
    elif mr['state'] == 'merged':
        close = True
    elif mr['state'] == 'closed':
        pass

    new_labels = list(set(new_labels))
    data = {"labels": ','.join(new_labels)}
    if close:
        data['state_event'] = 'close'

    return update_issue(project_id, issue_iid, data)


def fill_fields_based_on_issue(mr):
    """Complete the MR fields with data in its associated issue.

    If the MR doesn't have an assigned user, set to the issue's
    assignee.

    If the MR doesn't have a milestone, set it to the issue's
    milestone.
    """

    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    issue = get_issue(project_id, issue_iid)
    if issue is None:
        return

    data = {}
    if mr['milestone_id'] is None and issue.get('milestone'):
        data['milestone_id'] = issue['milestone']['id']
    if mr['assignee_id'] is None and len(issue.get('assignees', [])) == 1:
        data['assignee_id'] = issue['assignees'][0]['id']

    if data:
        return update_mr(project_id, mr['iid'], data)


def check_issue_reference_in_description(mr):
    issue_iid = get_related_issue_iid(mr)
    if issue_iid is None:
        return
    if f'#{issue_iid}' in mr['description']:
        # There is already a reference to the issue
        return
    project_id = mr['source_project_id']
    new_desc = f'Closes #{issue_iid} \r\n\r\n{mr["description"]}'
    return update_mr(project_id, mr['iid'], {'description': new_desc})


def add_multiple_merge_requests_label_if_needed(mr):
    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return
    if mr['state'] == 'closed':
        # Not adding this could mail the assertion below fail
        return

    related_mrs = get_related_merge_requests(
        mr['source_project_id'], issue_iid)

    # Discard closed merge requests, maybe they were created
    # accidentally and then closed
    related_mrs = [rmr for rmr in related_mrs
                   if rmr['state'] != 'closed']

    # Some MRs could be related to an issue only because they mentioned it,
    # not because they are implementing that issue
    related_mrs = [rmr for rmr in related_mrs
                   if str(issue_iid) in mr['source_branch']]

    assert any(rmr['iid'] == mr['iid']
               for rmr in related_mrs)

    if len(related_mrs) > 1:
        issue = get_issue(project_id, issue_iid)
        if issue is None or has_label(mr, 'multiple-merge-requests'):
            return
        new_labels = issue['labels']
        new_labels.append('multiple-merge-requests')
        new_labels = list(set(new_labels))
        data = {"labels": ','.join(new_labels)}
        return update_issue(project_id, issue_iid, data)


def get_related_issue_iid(mr):
    branch = mr['source_branch']
    try:
        iid = re.findall(branch_regex, branch)[0]
    except IndexError:
        return
    return int(iid)


def get_issue(project_id, iid):
    url = '{}/projects/{}/issues/{}'.format(
            API_PREFIX, project_id, iid)
    res = session.get(url)
    if res.status_code == 404:
        return
    res.raise_for_status()
    return res.json()


def get_related_merge_requests(project_id, issue_iid):
    url = '{}/projects/{}/issues/{}/related_merge_requests'.format(
            API_PREFIX, project_id, issue_iid)
    res = session.get(url)
    res.raise_for_status()
    return res.json()


def update_issue(project_id, iid, data):
    url = '{}/projects/{}/issues/{}'.format(
            API_PREFIX, project_id, iid)
    res = session.put(url, json=data)
    res.raise_for_status()
    return res.json()


if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)

