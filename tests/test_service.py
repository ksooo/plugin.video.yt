# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.service, fed with Kodi's announcements."""

import json
import time
from unittest import mock
from urllib.parse import parse_qs
from urllib.parse import urlsplit

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase
from tests.support import player_response
from tests.support import tokens

from resources.lib import addon
from resources.lib import feeds
from resources.lib import http
from resources.lib import innertube
from resources.lib import service
from resources.lib import watchtime

FILE = 'plugin://plugin.video.yt/play/?v=abc'

TRACKING = {'videostatsPlaybackUrl': {'baseUrl': 'https://s.youtube.com/api/stats/playback?a=1'},
            'videostatsWatchtimeUrl': {'baseUrl': 'https://s.youtube.com/api/stats/watchtime?a=1'}}


class ServiceTest(AddonTestCase):

    def setUp(self):
        super().setUp()
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        support.SETTINGS['sync_playback'] = True
        # What reached YouTube, in order: ('remove', video id) and
        # ('report', start, end, state).
        self.changes = []
        self.in_history = True
        self.failure = None
        for patcher in (mock.patch.object(innertube, 'remove_from_history', self._remove),
                        mock.patch.object(innertube, 'get_signed_in_player', self._player),
                        mock.patch.object(watchtime.http, 'request_json', self._request_json)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = service.Service()

    def _remove(self, video_id, language, region, access_token):
        if self.failure is not None:
            raise self.failure
        self.changes.append(('remove', video_id))
        return self.in_history

    @staticmethod
    def _player(video_id, language, region, access_token):
        return dict(player_response(video_id, lengthSeconds='200'), playbackTracking=TRACKING)

    def _request_json(self, method, url, headers, payload=None):
        params = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        if 'state' in params:
            self.changes.append(('report', params['st'], params['et'], params['state']))
        return {}

    def announce(self, method, file=FILE, **data):
        self.service.onNotification('xbmc', method, json.dumps(dict(data, file=file)))

    def play_count(self, playcount, file=FILE):
        self.announce('Files.OnPlayCountChanged', file, playcount=playcount)

    def resume_point(self, position, file=FILE):
        self.announce('Files.OnResumePointChanged', file,
                      resume={'position': position, 'total': 200.0 if position else 0.0})

    def later(self, seconds):
        self.service.handle_resets(time.monotonic() + seconds)

    def test_a_video_marked_watched_is_reported_watched_to_the_end(self):
        self.resume_point(0)
        self.play_count(1)
        self.later(service.PLAY_COUNT_WAIT_SECONDS)
        self.assertEqual(self.changes, [('report', '0.000', '200.000', 'stopped')])

    def test_playing_to_the_end_resets_the_resume_point_after_the_play_count(self):
        self.play_count(1)
        self.resume_point(0)
        self.later(service.PLAY_COUNT_WAIT_SECONDS)
        self.assertEqual(self.changes, [('report', '0.000', '200.000', 'stopped')])

    def test_a_reset_long_after_a_play_count_stands_on_its_own(self):
        with mock.patch.object(service.time, 'monotonic', return_value=1000.0):
            self.play_count(1)
        with mock.patch.object(service.time, 'monotonic',
                               return_value=1000.0 + service.PLAY_COUNT_WAIT_SECONDS):
            self.resume_point(0)
        self.service.handle_resets(1000.0 + 2 * service.PLAY_COUNT_WAIT_SECONDS)
        self.assertEqual(self.changes, [('report', '0.000', '200.000', 'stopped'),
                                        ('remove', 'abc')])

    def test_a_video_marked_unwatched_is_removed_from_the_history_once(self):
        self.resume_point(0)
        self.play_count(0)
        self.later(service.PLAY_COUNT_WAIT_SECONDS)
        self.assertEqual(self.changes, [('remove', 'abc')])

    def test_a_reset_resume_point_removes_the_video_after_a_while(self):
        self.resume_point(0)
        self.later(service.PLAY_COUNT_WAIT_SECONDS - 1)
        self.assertEqual(self.changes, [])
        self.later(service.PLAY_COUNT_WAIT_SECONDS)
        self.assertEqual(self.changes, [('remove', 'abc')])

    def test_a_resume_point_replaces_the_one_youtube_has(self):
        self.resume_point(50.0)
        self.assertEqual(self.changes, [('remove', 'abc'),
                                        ('report', '0.000', '50.000', 'stopped')])

    def test_the_listings_show_the_change_at_once(self):
        addon.save_json(addon.temp_path(feeds.PROGRESS_FILE),
                        {'saved_at': time.time(), 'progress': {'abc': 80, 'xyz': 10}})
        self.resume_point(50.0)
        self.assertEqual(feeds.watch_progress('access-vr'), {'abc': 25, 'xyz': 10})
        self.play_count(0)
        self.assertEqual(feeds.watch_progress('access-vr'), {'xyz': 10})

    def test_a_folder_of_the_add_on_is_listed_anew_once_per_change(self):
        support.INFO_LABELS['Container.FolderPath'] = 'plugin://plugin.video.yt/channel/?id=UC1'
        self.play_count(0)
        self.resume_point(50.0)
        self.assertEqual(support.BUILTINS, ['Container.Refresh', 'Container.Refresh'])

    def test_other_folders_are_left_as_they_are(self):
        support.INFO_LABELS['Container.FolderPath'] = 'videodb://movies/titles/'
        self.play_count(0)
        self.assertEqual(support.BUILTINS, [])

    def test_a_video_not_in_the_history_changes_no_folder(self):
        support.INFO_LABELS['Container.FolderPath'] = 'plugin://plugin.video.yt/history/'
        self.in_history = False
        self.play_count(0)
        self.assertEqual(support.BUILTINS, [])

    def test_other_files_are_left_alone(self):
        for file in ('/videos/film.mkv', 'plugin://plugin.video.other/play/?v=abc',
                     'plugin://plugin.video.yt/channel/?id=UC1'):
            self.play_count(1, file)
            self.resume_point(50.0, file)
        self.assertEqual(self.changes, [])

    def test_other_announcements_are_left_alone(self):
        self.service.onNotification('xbmc', 'VideoLibrary.OnUpdate',
                                    json.dumps({'item': {'id': 1, 'type': 'movie'}}))
        self.assertEqual(self.changes, [])

    def test_without_the_setting_nothing_is_synced(self):
        support.SETTINGS['sync_playback'] = False
        self.play_count(0)
        self.resume_point(50.0)
        self.assertEqual(self.changes, [])

    def test_without_sign_in_nothing_is_synced(self):
        support.reset()
        self.play_count(0)
        self.resume_point(50.0)
        self.assertEqual(self.changes, [])

    def test_a_failure_is_logged(self):
        self.failure = http.RequestError('timed out from https://www.youtube.com/')
        self.play_count(0)
        self.assertEqual(self.errors(),
                         ['[plugin.video.yt] timed out from https://www.youtube.com/'])
