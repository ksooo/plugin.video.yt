# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.playback, driven through the play route."""

import time
import xml.etree.ElementTree as ElementTree
from unittest import mock
from urllib.parse import parse_qs
from urllib.parse import urlsplit

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase
from tests.support import VP9_1080
from tests.support import VP9_HDR_1080
from tests.support import OPUS
from tests.support import player_response
from tests.support import tokens

from resources.lib import account
from resources.lib import addon
from resources.lib import feeds
from resources.lib import http
from resources.lib import innertube
from resources.lib import playback
from resources.lib import watchtime

MANIFEST_URL = 'http://127.0.0.1:12345/manifest.mpd'

TRACKING = {'videostatsPlaybackUrl': {'baseUrl': 'https://s.youtube.com/api/stats/playback?a=1'},
            'videostatsWatchtimeUrl': {'baseUrl': 'https://s.youtube.com/api/stats/watchtime?a=1'}}


class FakeManifestServer:
    """Records the manifest instead of serving it."""

    instances = []

    def __init__(self, manifest):
        self.manifest = manifest
        self.url = MANIFEST_URL
        self.served = None
        FakeManifestServer.instances.append(self)

    def serve(self, timeout_seconds, aborted):
        self.served = True
        return True


class PlaybackTestCase(AddonTestCase):

    def setUp(self):
        super().setUp()
        self.response = player_response('abc')
        self.client = innertube.ANDROID_VR
        self.player_requests = []
        FakeManifestServer.instances = []
        for patcher in (mock.patch.object(innertube, 'get_player', self._get_player),
                        mock.patch.object(playback, 'ManifestServer', FakeManifestServer)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _get_player(self, video_id, language, region, access_token):
        self.player_requests.append((video_id, language, region))
        self.access_token = access_token
        if isinstance(self.response, Exception):
            raise self.response
        return innertube.Player(self.response, self.client)

    def play(self, video_id='abc'):
        self.dispatch('play', '?v=' + video_id)
        return support.PLUGIN_STATE.get('resolved'), support.PLUGIN_STATE.get('resolved_item')

    @staticmethod
    def headers(list_item, name):
        return {key: values[0] for key, values in
                parse_qs(list_item.properties['inputstream.adaptive.' + name]).items()}


class VideoTest(PlaybackTestCase):

    def test_kodi_gets_the_manifest_server(self):
        resolved, list_item = self.play()
        self.assertTrue(resolved)
        self.assertEqual(list_item.path, FakeManifestServer.instances[0].url)
        self.assertTrue(FakeManifestServer.instances[0].served)

    def test_the_stream_is_played_by_isa_as_dash(self):
        _, list_item = self.play()
        self.assertEqual(list_item.properties['inputstream'], 'inputstream.adaptive')
        self.assertEqual(list_item.mime_type, 'application/dash+xml')
        self.assertFalse(list_item.content_lookup)

    def test_segments_are_fetched_as_the_client_that_was_served(self):
        _, list_item = self.play()
        self.assertEqual(self.headers(list_item, 'stream_headers'),
                         innertube.ANDROID_VR.stream_headers)

    def test_language_and_region_come_from_kodi(self):
        support.LANGUAGE[0] = 'fr'
        support.INFO_LABELS['System.Locale(iso)'] = 'CH'
        self.play('xyz')
        self.assertEqual(self.player_requests, [('xyz', 'fr', 'CH')])

    def test_the_signed_in_account_is_offered(self):
        self.play()
        self.assertIs(self.access_token, account.access_token)

    def test_hdr_is_the_default_on_an_hdr_display(self):
        self.response = player_response('abc', formats=(VP9_1080, VP9_HDR_1080, OPUS))
        support.INFO_LABELS['System.SupportedHDRTypes'] = 'HDR10, HLG'
        self.play()
        mpd = ElementTree.fromstring(FakeManifestServer.instances[0].manifest)
        default = mpd.find(".//{urn:mpeg:dash:schema:mpd:2011}AdaptationSet[@default='true']")
        self.assertEqual(default.get('name'), 'VP9 HDR10')

    def manifest(self):
        return ElementTree.fromstring(FakeManifestServer.instances[0].manifest)

    def test_the_video_codecs_are_those_of_the_setting(self):
        support.SETTINGS['video_codecs'] = ['avc1']
        self.play()
        codecs = [representation.get('codecs') for representation in self.manifest().iterfind(
            ".//{urn:mpeg:dash:schema:mpd:2011}AdaptationSet[@contentType='video']/"
            "{urn:mpeg:dash:schema:mpd:2011}Representation")]
        self.assertEqual(codecs, ['avc1.640028'])

    def test_the_caption_tracks_become_subtitles(self):
        self.response['captions'] = {'playerCaptionsTracklistRenderer': {'captionTracks': [
            {'baseUrl': 'https://www.youtube.com/api/timedtext?v=abc&fmt=srv3',
             'languageCode': 'de', 'name': {'simpleText': 'Deutsch'}}]}}
        self.play()
        subtitles = self.manifest().find(
            ".//{urn:mpeg:dash:schema:mpd:2011}AdaptationSet[@contentType='text']")
        self.assertEqual((subtitles.get('lang'), subtitles.get('name')), ('de', 'Deutsch'))

    def test_without_usable_formats_playback_fails(self):
        self.response = player_response('abc', formats=(OPUS,))
        resolved, _ = self.play()
        self.assertFalse(resolved)
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30100')])


class LiveTest(PlaybackTestCase):

    HLS_URL = 'https://manifest.googlevideo.com/api/manifest/hls_variant/id/abc/file/index.m3u8'

    def setUp(self):
        super().setUp()
        self.response = player_response('abc', formats=(), isLive=True)
        self.response['streamingData']['hlsManifestUrl'] = self.HLS_URL

    def test_kodi_gets_youtubes_hls_manifest(self):
        resolved, list_item = self.play()
        self.assertTrue(resolved)
        self.assertEqual(list_item.path, self.HLS_URL)
        self.assertEqual(list_item.properties['inputstream'], 'inputstream.adaptive')
        self.assertEqual(FakeManifestServer.instances, [])

    def test_manifest_and_segments_are_fetched_as_the_client_that_was_served(self):
        _, list_item = self.play()
        for name in ('manifest_headers', 'stream_headers'):
            self.assertEqual(self.headers(list_item, name), innertube.ANDROID_VR.stream_headers)

    def test_without_a_manifest_playback_fails(self):
        del self.response['streamingData']['hlsManifestUrl']
        resolved, _ = self.play()
        self.assertFalse(resolved)
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30100')])


class FailureTest(PlaybackTestCase):

    def test_youtubes_reason_is_shown(self):
        self.response = innertube.PlayabilityError('Video unavailable')
        resolved, _ = self.play()
        self.assertFalse(resolved)
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'Video unavailable')])

    def test_the_need_to_sign_in_is_shown_instead_of_youtubes_reason(self):
        self.response = innertube.PlayabilityError('This video may be inappropriate',
                                                   sign_in_would_help=True)
        self.play()
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30102')])

    def test_without_a_reason_a_generic_message_is_shown(self):
        self.response = innertube.PlayabilityError('')
        self.play()
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30100')])

    def test_a_network_failure_is_shown_and_logged(self):
        self.response = http.RequestError('timed out from https://www.youtube.com/')
        resolved, _ = self.play()
        self.assertFalse(resolved)
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30101')])
        self.assertEqual(self.errors(),
                         ['[plugin.video.yt] timed out from https://www.youtube.com/'])


class SyncTest(PlaybackTestCase):

    def setUp(self):
        super().setUp()
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        support.SETTINGS['sync_playback'] = True
        self.response['playbackTracking'] = TRACKING
        self.reports = []
        self.report_failure = None
        self.tracking_requests = []
        for patcher in (mock.patch.object(watchtime.http, 'request_json', self._request_json),
                        mock.patch.object(innertube, 'get_signed_in_player',
                                          self._get_signed_in_player)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _request_json(self, method, url, headers, payload=None):
        self.reports.append((method, url, headers))
        if self.report_failure is not None:
            raise self.report_failure
        return {}

    def _get_signed_in_player(self, video_id, language, region, access_token):
        self.tracking_requests.append((video_id, access_token))
        return dict(player_response(video_id), playbackTracking=TRACKING)

    @staticmethod
    def watch(seconds, start=0, paused=()):
        """Have Kodi play the manifest from start for the seconds given, then stop."""
        support.PLAYBACK[:] = [(MANIFEST_URL, start + second, second in paused)
                               for second in range(seconds + 1)]

    def reported(self):
        """Return the reports sent as (state, start, end); all None for the start's."""
        reports = []
        for _, url, _ in self.reports:
            params = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
            reports.append((params.get('state'), params.get('st'), params.get('et')))
        return reports

    def test_playback_is_reported_at_the_start_every_ten_seconds_and_at_the_end(self):
        self.watch(25)
        self.play()
        self.assertEqual(self.reported(), [(None, None, None),
                                           ('playing', '0.000', '10.000'),
                                           ('playing', '10.000', '20.000'),
                                           ('stopped', '20.000', '25.000')])

    def test_reports_go_to_the_tracking_urls_as_the_signed_in_vr_app(self):
        self.watch(10)
        self.play()
        urls = [urlsplit(url) for _, url, _ in self.reports]
        self.assertEqual([url.path for url in urls],
                         ['/api/stats/playback', '/api/stats/watchtime', '/api/stats/watchtime'])
        nonces = {parse_qs(url.query)['cpn'][0] for url in urls}
        self.assertEqual(len(nonces), 1)
        for method, _, headers in self.reports:
            self.assertEqual((method, headers),
                             ('GET', dict(innertube.ANDROID_VR.stream_headers,
                                          Authorization='Bearer access-vr')))

    def test_a_pause_is_reported(self):
        self.watch(12, paused=(10, 11, 12))
        self.play()
        self.assertEqual(self.reported()[1], ('paused', '0.000', '10.000'))

    def test_a_resumed_video_is_reported_from_where_it_resumed(self):
        self.watch(5, start=100)
        self.play()
        self.assertEqual(self.reported()[-1], ('stopped', '100.000', '105.000'))

    def test_when_the_vr_app_served_the_video_its_urls_are_taken(self):
        self.watch(1)
        self.play()
        self.assertEqual(self.tracking_requests, [])

    def test_when_android_served_the_video_the_vr_app_is_asked_for_the_urls(self):
        self.client = innertube.ANDROID
        self.watch(1)
        self.play()
        self.assertEqual(self.tracking_requests, [('abc', 'access-vr')])
        self.assertEqual(len(self.reports), 2)

    def test_without_the_setting_nothing_is_reported(self):
        support.SETTINGS['sync_playback'] = False
        self.watch(25)
        self.play()
        self.assertEqual(self.reports, [])

    def test_without_sign_in_nothing_is_reported(self):
        support.reset()
        self.client = innertube.ANDROID
        self.watch(25)
        self.play()
        self.assertEqual((self.reports, self.tracking_requests), ([], []))

    def test_live_streams_are_not_reported(self):
        self.response = player_response('abc', formats=(), isLive=True,
                                        playbackTracking=TRACKING)
        self.response['streamingData']['hlsManifestUrl'] = 'https://manifest.googlevideo.com/x'
        self.watch(25)
        self.play()
        self.assertEqual(self.reports, [])

    def test_a_playback_that_never_starts_is_not_reported(self):
        self.play()
        self.assertEqual(self.reports, [])

    def test_playing_something_else_ends_the_playback(self):
        support.PLAYBACK[:] = [(MANIFEST_URL, 0, False), (MANIFEST_URL, 1, False),
                               ('http://127.0.0.1:23456/manifest.mpd', 0, False)]
        self.play()
        self.assertEqual(self.reported()[-1], ('stopped', '0.000', '1.000'))

    def test_shutting_down_kodi_sends_no_more_reports(self):
        self.watch(25)
        support.ABORT_REQUESTED[0] = True
        self.play()
        self.assertEqual(self.reported(), [(None, None, None)])

    def test_failing_reports_are_logged_and_reporting_goes_on(self):
        self.report_failure = http.RequestError('HTTP 500 from https://s.youtube.com/')
        self.watch(10)
        self.play()
        self.assertEqual(len(self.reports), 3)
        self.assertEqual(len(self.errors()), 3)

    def test_where_playback_stopped_shows_in_the_listings_at_once(self):
        addon.save_json(addon.temp_path(feeds.PROGRESS_FILE),
                        {'saved_at': time.time(), 'progress': {}})
        self.watch(106)
        self.play()
        self.assertEqual(feeds.watch_progress('access-vr'), {'abc': 50})
