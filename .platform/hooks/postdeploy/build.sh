#!/usr/bin/env bash
cd /var/app/current/
source /var/app/venv/staging-LQM1lest/bin/activate
pip install .
pip install -r requirements.txt
exit 0