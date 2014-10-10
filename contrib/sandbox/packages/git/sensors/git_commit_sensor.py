#!/usr/bin/env python

# Requirements
# pip install gitpython
# Also requires git CLI tool to be installed.

import datetime
try:
    import simplejson as json
except ImportError:
    import json
import os
import time

from git.repo import Repo

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'git_config.json')


class GitCommitSensor(object):
    def __init__(self, container_service):
        self._config_file = CONFIG_FILE
        self._container_service = container_service
        self._poll_interval = 5  # seconds.
        self._logger = self._container_service.get_logger(__name__)
        self._old_head = None

    def setup(self):
        git_opts = self._get_config()

        if git_opts['url'] is None:
            raise Exception('Remote git URL not set.')
        self._url = git_opts['url']
        self._branch = git_opts.get('branch', 'master')
        default_clone_dir = os.path.join(os.path.dirname(__file__), 'clones')
        self._local_path = git_opts.get('local_clone_path', default_clone_dir)
        self._poll_interval = git_opts.get('poll_interval', self._poll_interval)

        if os.path.exists(self._local_path):
            self._repo = Repo.init(self._local_path)
        else:
            try:
                self._repo = Repo.clone_from(self._url, self._local_path)
            except Exception:
                self._logger.exception('Unable to clone remote repo from %s',
                                       self._url)
                raise

    def start(self):
        while True:
            # head = self._repo.commit_info(start=0, end=1)[0]
            head = self._repo.commit()
            head_sha = head.hexsha

            if not self._old_head:
                self._old_head = head_sha
                if len(self._repo.heads) == 1:  # There is exactly one commit. Kick off a trigger.
                    self._dispatch_trigger(head)
                continue

            if head_sha != self._old_head:
                try:
                    self._dispatch_trigger(head)
                except Exception:
                    self._logger.exception('Failed dispatching trigger.')
                else:
                    self._old_head = head_sha

            time.sleep(self._poll_interval)

    def stop(self):
        pass

    def get_trigger_types(self):
        return [{
            'name': 'st2.git.head_sha_monitor',
            'description': 'Stackstorm git commits tracker',
            'payload_schema': {
                'type': 'object',
                'properties': {
                    'author': {'type': 'string'},
                    'author_email': {'type', 'string'},
                    'authored_date': {'type': 'string'},
                    'author_tz_offset': {'type': 'string'},
                    'committer': {'type': 'string'},
                    'committer_email': {'type': 'string'},
                    'committed_date': {'type': 'string'},
                    'committer_tz_offset': {'type': 'string'},
                    'revision': {'type': 'string'}
                }
            }
        }]

    def add_trigger(self, trigger):
        pass

    def update_trigger(self, trigger):
        pass

    def remove_trigger(self, trigger):
        pass

    def _dispatch_trigger(self, commit):
        trigger = {}
        trigger['name'] = 'st2.git.head_sha_monitor'
        payload = {}
        payload['revision'] = str(commit)
        payload['author'] = commit.author.name
        payload['author_email'] = commit.author.email
        payload['authored_date'] = self._to_date(commit.authored_date)
        payload['author_tz_offset'] = commit.author_tz_offset
        payload['committer'] = commit.committer.name
        payload['committer_email'] = commit.committer.email
        payload['committed_date'] = self._to_date(commit.committed_date)
        payload['committer_tz_offset'] = commit.committer_tz_offset
        self._container_service.dispatch(trigger, payload)

    def _get_config(self):
        if not os.path.exists(self._config_file):
            raise Exception('Config file not found at %s.' % self._config_file)
        with open(self._config_file) as f:
            return json.load(f)

    def _to_date(self, ts_epoch):
        return datetime.datetime.fromtimestamp(ts_epoch).strftime('%Y-%m-%dT%H:%M:%SZ')
