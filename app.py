from flask import Flask, request, abort
from datetime import datetime
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def homepage():
    json = request.get_json()
    if json is None:
        abort(400)
    # print('Arrived request', json)
    if json.get('object_kind') != 'merge_request':
        return 'I only process merge requests right now!'
    mr = json['object_attributes']
    if mr['title'].startswith('WIP:'):
        return 'Ignoring WIP MR'
    print("Processing MR #", mr['id'])
    return 'OK'

if __name__ == '__main__':
    app.run(debug=True, use_reloader=True)

