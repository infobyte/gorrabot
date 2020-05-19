#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2019  Infobyte LLC (http://www.infobytesec.com/)

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""The setup script."""

import sys
from re import search
from setuptools import setup, find_packages

with open('gorrabot/__init__.py', 'rt', encoding='utf8') as f:
    version = search(r'__version__ = \'(.*?)\'', f.read()).group(1)

with open('README.md') as readme_file:
    readme = readme_file.read()
history = readme

requirements = ['requests', 'flask']

setup(
    author="Matias Lang",
    author_email='***REMOVED***@infobytesec.com',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    description="Gitlab bot made to automate checks and processes in the Faraday development.",
    entry_points={
        'console_scripts': [
            'gorrabot=gorrabot.app:main',
            'gorrabot-slack-resume=gorrabot.slack_resume:main',
            'gorrabot-comment-stale-mr=gorrabot.comment_stale_merge_requests:main',
        ],
    },
    install_requires=requirements,
    license="GNU General Public License v3",
    long_description=readme,
    long_description_content_type='text/markdown',
    include_package_data=True,
    keywords='',
    name='gorrabot',
    packages=find_packages(include=['gorrabot', 'gorrabot.*']),
    use_scm_version=False,
    setup_requires=[],
    version=version,
    zip_safe=False,
)
