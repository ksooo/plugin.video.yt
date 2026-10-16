# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.playback, driven through the play route."""

import xml.etree.ElementTree as ElementTree
from unittest import mock
from urllib.parse import parse_qs

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase
from tests.support import VP9_1080
from tests.support import VP9_HDR_1080
from tests.support import OPUS
from tests.support import player_response

from resources.lib import account
from resources.lib import http
from resources.lib import innertube
from resources.lib import playback


class FakeManifestServer:
    """Records the manifest instead of serving it."""

    instances = []

    def __init__(self, manifest):
        self.manifest = manifest
        self.url = 'http://127.0.0.1:12345/manifest.mpd'
        self.served = None
        FakeManifestServer.instances.append(self)

    def serve(self, timeout_seconds, aborted):
        self.served = True
        return True


class PlaybackTestCase(AddonTestCase):

    def setUp(self):
        super().setUp()
        self.response = player_response('abc')
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
        return innertube.Player(self.response, innertube.ANDROID_VR)

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
