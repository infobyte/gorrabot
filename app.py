import os
import re
import datetime
import requests
from urllib.parse import quote
from flask import Flask, request, abort
app = Flask(__name__)

TOKEN = os.environ['GITLAB_TOKEN']
REQUEST_TOKEN = os.environ['GITLAB_CHECK_TOKEN']
SELF_USERNAME = os.environ['GITLAB_BOT_USERNAME']

API_PREFIX = 'https://gitlab.com/api/v4'

OLD_MEMBERS = [
    '***REMOVED***', '***REMOVED***', '***REMOVED***', '***REMOVED***', '***REMOVED***',
    '***REMOVED***', '***REMOVED***']

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
MSG_NEW_MR_CREATED = (
    'Vi que pusheaste a este branch pero no había ningún merge request '
    'creado. Me tomé la molestia de crearlo por vos, usando la información '
    'de un merge request de ***REMOVED***. Si tenés que hacer más cambios (es decir, '
    'no se trata de un simple merge), poné el MR en WIP para aclarar que '
    'todavía no está terminado.'
)
MSG_CHECK_SUPERIOR_MR = (
    'Noté que mergeaste el branch que implementa esto para una versión '
    'anterior (***REMOVED*** o ***REMOVED***). Hay que mergear este MR también para evitar que '
    'haya conflictos entre ***REMOVED***/dev, ***REMOVED***/dev y ***REMOVED***/dev.'
)
MSG_STALE_MR = """
Noté que este merge request está en WIP y sin actividad hace bastante tiempo.
Para evitar que quede obsoleto e inmergeable, estaría bueno mirarlo. Te
recomiendo proceder con alguna de estas acciones:

* Si ya está listo para mergear, sacale el `WIP: ` del título y esperá a que
  reciba feedback
* Si se trata de un merge request experimental o pensado a largo plazo, cambiá
  el nombre del source branch de `tkt_....` a `exp_....` para que lo tenga en
  cuenta
* Si te parece que los cambios no son más requeridos, cerrá el merge request
* En caso contrario, hacé las modificaciones que sean necesarias y sacarle
  el WIP
* También se puede agregar el label especial `no-me-apures` para que no vuelva
  a mostrar este mensaje en este merge request. Esto es una inhibición de mis
  gorra-poderes así que prefiero que no se abuse de esta opción
"""
MSG_MR_OLD_MEMBER = (
    '@***REMOVED***: Este merge request no está listo y está asignado a un usuario '
    'que ya no forma parte del equipo. Habría que cerrarlo o reasignárselo a '
    'alguien más'
)

# Define inactivity as a merge request whose last commit is older than
# now() - inactivity_time
inactivity_time = datetime.timedelta(days=30)

# Time to wait until a new message indicating the MR is stale is created
stale_mr_message_interval = datetime.timedelta(days=7)

# Time to wait until a new message indicating the MR is stale is created
decision_issue_message_interval = datetime.timedelta(days=0)

branch_regex = r'***REMOVED***'

session = requests.Session()
session.headers['Private-Token'] = TOKEN


@app.route('/status')
def status():
    return "OK"


@app.route('/webhook', methods=['POST'])
def homepage():
    if request.headers.get('X-Gitlab-Token') != REQUEST_TOKEN:
        abort(403)
    json = request.get_json()
    if json is None:
        abort(400)

    if json.get('object_kind') == 'push':
        return handle_push(json)

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
    if mr['state'] == 'merged':
        notify_unmerged_superior_mrs(mr)
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


def handle_push(push):
    prefix = 'refs/heads/'
    if not push['ref'].startswith(prefix):
        msg = f'Unknown ref name {push["ref"]}'
        print(msg)
        return msg
    branch_name = push['ref'][len(prefix):]

    if '/dev' in branch_name:
        retry_conflict_check_of_mrs_with_target_branch(
            push['project_id'],
            branch_name
        )

    if '***REMOVED***' in branch_name:
        parent_branches = [
            branch_name.replace('***REMOVED***', '***REMOVED***')
        ]
    elif '***REMOVED***' in branch_name:
        # keep ***REMOVED*** first so ensure_upper_version_is_created
        # won't create a MR based on another MR automatically
        # created by gorrabot
        parent_branches = [
            branch_name.replace('***REMOVED***', '***REMOVED***'),
            branch_name.replace('***REMOVED***', '***REMOVED***'),
        ]
    else:
        parent_branches = []

    for parent_branch_name in parent_branches:
        retry_merge_conflict_check_of_branch(
            push['project_id'], parent_branch_name
        )

    if push['checkout_sha'] is not None:
        # Deleting a branch triggers a push event, and I don't want
        # that to create a new MR. So check that the branch wasn't
        # deleted by checking the checkout_sha.
        # See https://gitlab.com/gitlab-org/gitlab-ce/issues/54216
        ensure_upper_version_is_created(
            push['project_id'],
            branch_name,
            parent_branches
        )

    return 'OK'


def get_username(data):
    if data.get('assignee'):
        return data['assignee']['username']
    elif data.get('author'):
        return data['author']['username']

    user_id = data['object_attributes']['author_id']
    res = session.get(API_PREFIX + '/users/{}'.format(user_id))
    res.raise_for_status()
    return res.json()['username']


def get_usernames_from_mr_or_issue(data):
    if len(data.get('assignees')):
        return [assignee['username'] for assignee in data['assignees']]
    elif data.get('author'):
        return [data['author']['username']]

    user_id = data['object_attributes']['author_id']
    res = session.get(API_PREFIX + '/users/{}'.format(user_id))
    res.raise_for_status()
    return [res.json()['username']]


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

def get_mr(project_id, iid):
    url = f'{API_PREFIX}/projects/{project_id}/merge_requests/{iid}'
    res = session.get(url)
    res.raise_for_status()
    return res.json()


def get_mr_last_commit(mr):
    project_id = mr['source_project_id']
    url = mr_url(project_id, mr['iid']) + '/commits'
    res = session.get(url)
    res.raise_for_status()
    try:
        return res.json()[0]
    except IndexError:
        return


def get_branch_last_commit(project_id, branch_name):
    branch = get_branch(project_id, branch_name)
    if branch is None:
        return
    return branch['commit']


def get_changed_files(changes):
    return set(change['new_path'] for change in changes)


def comment_mr(project_id, iid, body, can_be_duplicated=True, min_time_between_comments=None):
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
    elif min_time_between_comments is not None:
        # The comment can be duplicated, but to avoid flooding, wait at least
        # min_time_between_comments to duplicate them
        # Ugly hack to drop user mentions from body
        search_title = body.split(': ', 1)[-1]
        res = session.get(mr_url(project_id, iid) + '/notes')
        res.raise_for_status()
        comments = res.json()

        def is_recent_comment(comment):
            time_passed = datetime.datetime.utcnow() - parse_api_date(
                    comment['created_at'])
            return time_passed < min_time_between_comments

        if any(is_recent_comment(comment) and
               search_title.strip() in comment['body'].strip()
               for comment in comments):
            return

    url = mr_url(project_id, iid) + '/notes'
    data = {"body": body}
    res = session.post(url, json=data)
    res.raise_for_status()
    return res.json()


def parse_api_date(date):
    assert date.endswith('Z')
    return datetime.datetime.fromisoformat(date[:-1])


def create_mr(project_id, mr_data):
    url = (
        f"{API_PREFIX}/projects/{project_id}/"
        f"merge_requests"
    )
    res = session.post(url, json=mr_data)
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
    Pending merge/approval MR -> Label issue as test
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

    if 'milestone_id' in mr:
        # This comes from the webhook data
        milestone_id = mr['milestone_id']
    else:
        milestone_id = mr['milestone'] and mr['milestone']['id']

    if 'assignee_id' in mr:
        # This comes from the webhook data
        assignee_id = mr['assignee_id']
    else:
        assignee_id = mr['assignee'] and mr['assignee']['id']

    if milestone_id is None and issue.get('milestone'):
        data['milestone_id'] = issue['milestone']['id']
    if assignee_id is None and len(issue.get('assignees', [])) == 1:
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


def retry_merge_conflict_check_of_branch(project_id, branch_name):
    last_commit = get_branch_last_commit(project_id, branch_name)
    if last_commit is None:
        return
    jobs = get_commit_jobs(project_id, last_commit['id'])
    try:
        mc_check_job = next(job for job in jobs
                            if job['name'] == 'merge_conflict_check')
    except StopIteration:
        return
    print(f'Retrying merge conflict check job for branch '
          f'{branch_name}')
    retry_job(project_id, mc_check_job['id'])


def retry_conflict_check_of_mrs_with_target_branch(project_id, target_branch):
    """Find all MRs with the specified target branch, and in the current
    or upcoming milestones. Retry the merge conflict check job of all of
    them"""
    merge_requests = get_merge_requests(
        project_id,
        {'target_branch': target_branch, 'state': 'opened'}
    )

    # This will ignore merge requests of old milestones
    # merge_requests = filter_current_or_upcoming_mrs(merge_requests)

    for mr in merge_requests:
        retry_merge_conflict_check_of_branch(
            project_id,
            mr['source_branch']
        )


def ensure_upper_version_is_created(project_id, branch_name, parent_branches):
    """If there exists a MR with a source branch that is in
    parent_branches and there is no MR whose source branch is
    branch_name, create a new MR inheriting from the parent MR.
    
    Exclude all closed MRs from this logic.
    """

    mrs_for_this_branch = get_merge_requests(
        project_id,
        {'source_branch': branch_name}
    )
    if any(mr['state'] != 'closed' for mr in mrs_for_this_branch):
        return


    parent_mr = None
    for parent_branch_name in parent_branches:
        merge_requests = get_merge_requests(
            project_id,
            {'source_branch': parent_branch_name}
        )
        merge_requests = [
            mr for mr in merge_requests
            if mr['state'] != 'closed'
        ]
        if len(merge_requests) == 1:
            # If the length is greater than 1, I don't know which branch should
            # I use.
            parent_mr = merge_requests[0]
            break

    if parent_mr is None:
        return

    mr_data = create_similar_mr(parent_mr, branch_name)
    new_mr = create_mr(parent_mr['source_project_id'], mr_data)
    fill_fields_based_on_issue(new_mr)
    username = get_username(parent_mr)
    comment_mr(
        project_id,
        new_mr['iid'],
        f'@{username}: {MSG_NEW_MR_CREATED}'
    )


def notify_unmerged_superior_mrs(mr):
    """Warn the user who merged mr if there also are ***REMOVED*** or ***REMOVED*** merge
    requests for the same issue."""
    assert mr['state'] == 'merged'
    issue_iid = get_related_issue_iid(mr)
    project_id = mr['source_project_id']
    if issue_iid is None:
        return

    related_mrs = get_related_merge_requests(
        project_id, issue_iid)
    related_mrs = [rmr for rmr in related_mrs
                   if rmr['state'] not in ('merged', 'closed')]

    if '***REMOVED***' in mr['source_branch']:
        expected_versions = ['***REMOVED***', '***REMOVED***']
    elif '***REMOVED***' in mr['source_branch']:
        expected_versions = ['***REMOVED***']

    global_branch_name = remove_version(mr['source_branch'])

    # Discard MRs with different branch names (besides ***REMOVED***/***REMOVED***/***REMOVED***)
    related_mrs = [
        rmr for rmr in related_mrs
        if remove_version(rmr['source_branch']) == global_branch_name
    ]

    # Discard MRs that are not of expected_versions
    related_mrs = [
        rmr for rmr in related_mrs
        if any(version in rmr['source_branch']
               for version in expected_versions)
    ]

    # The data from the webhook doesn't contain merged_by
    mr = get_mr(project_id, mr['iid'])

    username = mr['merged_by']['username']
    for rmr in related_mrs:
        comment_mr(
            project_id,
            rmr['iid'],
            f'@{username}: {MSG_CHECK_SUPERIOR_MR}',
            can_be_duplicated=False,
        )


def remove_version(branch: str):
    return branch.replace('***REMOVED***', 'xxx').replace('***REMOVED***', 'xxx').replace('***REMOVED***', 'xxx')


def create_similar_mr(parent_mr, source_branch):
    assert '***REMOVED***' in source_branch or '***REMOVED***' in source_branch
    if '***REMOVED***' in source_branch:
        target_branch = '***REMOVED***/dev'
    elif '***REMOVED***' in source_branch:
        target_branch = '***REMOVED***/dev'
    new_title = (
        f"{parent_mr['title']} ({target_branch.replace('/dev','')} edition)"
    )
    # if not new_title.startswith('WIP: '):
    #     new_title = 'WIP: ' + new_title
    new_description = (
        f"""
{parent_mr['description']}

Created with <3 by @gorrabot, based on merge request
!{parent_mr['iid']}
        """
    )

    new_labels = set(parent_mr['labels'])
    new_labels.add('no-changelog')
    new_labels = list(new_labels)

    mr = {
        'source_branch': source_branch,
        'target_branch': target_branch,
        'title': new_title,
        'description': new_description,
        'labels': new_labels
    }
    return mr


def filter_current_or_upcoming_mrs(merge_requests):
    for mr in merge_requests:
        milestone = mr['milestone']
        if not milestone:
            continue
        if milestone['state'] != 'active':
            continue
        if ('upcoming' in milestone['title'] or
                'current' in milestone['title']):
            yield mr


def get_related_issue_iid(mr):
    branch = mr['source_branch']
    try:
        iid = re.findall(branch_regex, branch)[0]
    except IndexError:
        return
    return int(iid)


def get_issues(project_id, filters={}):
    url = f'{API_PREFIX}/projects/{project_id}/issues'
    res = session.get(url, params=filters)
    res.raise_for_status()
    return res.json()


def get_issue(project_id, iid):
    url = '{}/projects/{}/issues/{}'.format(
            API_PREFIX, project_id, iid)
    res = session.get(url)
    if res.status_code == 404:
        return
    res.raise_for_status()
    return res.json()


def get_merge_requests(project_id, filters={}):
    url = f'{API_PREFIX}/projects/{project_id}/merge_requests'
    res = session.get(url, params=filters)
    res.raise_for_status()
    return res.json()


def get_staled_merge_requests(project_id, wip=None):
    filters = {
        'scope': 'all',
        'wip': wip,
        'state': 'opened',
        'per_page': 100,
    }
    mrs = get_merge_requests(project_id, filters)
    for mr in mrs:
        if 'no-me-apures' in mr['labels']:
            continue
        if mr['source_branch'] and mr['source_branch'].startswith('exp_'):
            continue
        last_commit = get_mr_last_commit(mr)
        if last_commit is None:
            # There is no activity in the MR, use the MR's creation date
            created_at = parse_api_date(mr['created_at'])
        else:
            created_at = parse_api_date(last_commit['created_at'])
        if datetime.datetime.utcnow() - created_at > inactivity_time:
            yield mr


def get_related_merge_requests(project_id, issue_iid):
    url = '{}/projects/{}/issues/{}/related_merge_requests'.format(
            API_PREFIX, project_id, issue_iid)
    res = session.get(url)
    res.raise_for_status()
    return res.json()


def get_decision_issues(project_id):
    filters = {
        'scope': 'all',
        'state': 'opened',
        'labels': 'waiting-decision',
        'per_page': 100,
    }
    issues = get_issues(project_id, filters)
    for issue in issues:
        if 'no-me-apures' in issue['labels']:
            continue
        updated_at = parse_api_date(issue['updated_at'])
        if datetime.datetime.utcnow() - updated_at > decision_issue_message_interval:
            yield issue


def get_accepted_issues(project_id):
    filters = {
        'scope': 'all',
        'labels': 'Accepted',
        'state': 'opened',
        'per_page': 100,
    }
    return get_issues(project_id, filters)


def get_branch(project_id, branch_name):
    url = f'{API_PREFIX}/projects/{project_id}/repository/branches/{quote(branch_name, safe="")}'
    res = session.get(url)
    if res.status_code == 404:
        return
    res.raise_for_status()
    return res.json()


def get_commit_jobs(project_id, commit_id):
    url = (f'{API_PREFIX}/projects/{project_id}/repository/'
           f'commits/{commit_id}/statuses')
    res = session.get(url)
    res.raise_for_status()
    return res.json()


def retry_job(project_id, job_id):
    url = f'{API_PREFIX}/projects/{project_id}/jobs/{job_id}/retry'
    res = session.post(url)
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

