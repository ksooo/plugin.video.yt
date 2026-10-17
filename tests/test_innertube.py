# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.innertube."""

import unittest
from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests.support import player_response

from resources.lib import innertube

def compact_video(video_id):
    return {'compactVideoRenderer': {'videoId': video_id,
                                     'title': {'runs': [{'text': 'Title ' + video_id}]}}}


def browse_response(*sections):
    return {'contents': {'singleColumnBrowseResultsRenderer': {'tabs': [
        {'tabRenderer': {'content': {'sectionListRenderer': {'contents': list(sections)}}}},
    ]}}}


BOT_CHECK = {
    'playabilityStatus': {'status': 'LOGIN_REQUIRED',
                          'reason': 'Sign in to confirm you are not a bot'},
    'responseContext': {'visitorData': 'visitor-1'},
}

TRACKING = {'videostatsPlaybackUrl': {'baseUrl': 'https://s.youtube.com/api/stats/playback?a=1'},
            'videostatsWatchtimeUrl': {'baseUrl': 'https://s.youtube.com/api/stats/watchtime?a=1'}}


class PlayerTest(unittest.TestCase):

    def setUp(self):
        self.requests = []
        # Responses by client name; a list is answered from front to back.
        self.responses = {'ANDROID': player_response('abc'),
                          'ANDROID_VR': player_response('abc')}
        self.tokens = {}
        self.tokens_asked = []
        patcher = mock.patch.object(innertube.http, 'post_json', self._post_json)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post_json(self, url, payload, headers):
        self.requests.append((payload, headers))
        response = self.responses[payload['context']['client']['clientName']]
        return response.pop(0) if isinstance(response, list) else response

    def get_player(self, video_id, language, region):
        return innertube.get_player(video_id, language, region, self._access_token)

    def _access_token(self, account):
        self.tokens_asked.append(account)
        return self.tokens.get(account)

    def clients_asked(self):
        return [payload['context']['client']['clientName'] for payload, _ in self.requests]

    def test_android_is_asked_first(self):
        player = self.get_player('abc', 'de', 'DE')
        self.assertEqual(self.clients_asked(), ['ANDROID'])
        self.assertIs(player.client, innertube.ANDROID)
        self.assertEqual(player.response, self.responses['ANDROID'])

    def test_the_request_identifies_as_the_client(self):
        self.get_player('abc', 'de', 'DE')
        payload, headers = self.requests[0]
        self.assertEqual(payload['videoId'], 'abc')
        self.assertEqual(payload['params'], '2AMB')
        self.assertEqual(headers['User-Agent'], innertube.ANDROID.stream_headers['User-Agent'])
        self.assertEqual(headers['X-YouTube-Client-Name'], '3')

    def test_language_and_region_are_passed_on(self):
        self.get_player('abc', 'de', 'AT')
        client = self.requests[0][0]['context']['client']
        self.assertEqual((client['hl'], client['gl']), ('de', 'AT'))

    def test_unknown_language_and_region_are_left_out(self):
        self.get_player('abc', '', '')
        client = self.requests[0][0]['context']['client']
        self.assertNotIn('hl', client)
        self.assertNotIn('gl', client)

    def test_vr_steps_in_when_android_is_refused(self):
        self.responses['ANDROID'] = {'playabilityStatus': {'status': 'UNPLAYABLE'}}
        player = self.get_player('abc', 'de', 'DE')
        self.assertEqual(self.clients_asked(), ['ANDROID', 'ANDROID_VR'])
        self.assertIs(player.client, innertube.ANDROID_VR)

    def test_the_bot_check_is_passed_with_the_visitor_id(self):
        self.responses['ANDROID'] = [BOT_CHECK, player_response('abc')]
        player = self.get_player('abc', 'de', 'DE')

        self.assertEqual(self.clients_asked(), ['ANDROID', 'ANDROID'])
        payload, headers = self.requests[1]
        self.assertEqual(payload['context']['client']['visitorData'], 'visitor-1')
        self.assertEqual(headers['X-Goog-Visitor-Id'], 'visitor-1')
        self.assertIs(player.client, innertube.ANDROID)

    def test_a_refusal_carries_youtubes_reason(self):
        self.responses['ANDROID'] = {'playabilityStatus': {'status': 'ERROR'}}
        self.responses['ANDROID_VR'] = {'playabilityStatus': {
            'status': 'LOGIN_REQUIRED', 'reason': 'Sign in to confirm your age'}}
        with self.assertRaises(innertube.PlayabilityError) as context:
            self.get_player('abc', 'de', 'DE')
        self.assertEqual(str(context.exception), 'Sign in to confirm your age')

    def test_a_refusal_without_reason_is_still_one(self):
        self.responses['ANDROID'] = {'playabilityStatus': {'status': 'ERROR'}}
        self.responses['ANDROID_VR'] = {'playabilityStatus': {'status': 'ERROR'}}
        with self.assertRaises(innertube.PlayabilityError) as context:
            self.get_player('abc', 'de', 'DE')
        self.assertEqual(str(context.exception), '')

    def test_android_is_asked_without_signing_in(self):
        self.tokens = {'vr': 'access-vr'}
        self.get_player('abc', 'de', 'DE')
        self.assertEqual(self.tokens_asked, [])
        self.assertNotIn('Authorization', self.requests[0][1])

    def test_vr_is_asked_signed_in(self):
        self.tokens = {'vr': 'access-vr'}
        self.responses['ANDROID'] = {'playabilityStatus': {'status': 'LOGIN_REQUIRED'}}
        self.get_player('abc', 'de', 'DE')
        self.assertEqual(self.tokens_asked, ['vr'])
        self.assertEqual(self.requests[1][1]['Authorization'], 'Bearer access-vr')

    def test_vr_is_asked_anonymously_without_sign_in(self):
        self.responses['ANDROID'] = {'playabilityStatus': {'status': 'LOGIN_REQUIRED'}}
        self.get_player('abc', 'de', 'DE')
        self.assertNotIn('Authorization', self.requests[1][1])

    def test_signing_in_would_help_with_an_age_check(self):
        refusal = {'playabilityStatus': {'status': 'LOGIN_REQUIRED',
                                         'reason': 'This video may be inappropriate'}}
        self.responses = {'ANDROID': refusal, 'ANDROID_VR': refusal}
        with self.assertRaises(innertube.PlayabilityError) as context:
            self.get_player('abc', 'de', 'DE')
        self.assertTrue(context.exception.sign_in_would_help)

    def test_signing_in_would_not_help_when_signed_in(self):
        self.tokens = {'vr': 'access-vr'}
        refusal = {'playabilityStatus': {'status': 'LOGIN_REQUIRED'}}
        self.responses = {'ANDROID': refusal, 'ANDROID_VR': refusal}
        with self.assertRaises(innertube.PlayabilityError) as context:
            self.get_player('abc', 'de', 'DE')
        self.assertFalse(context.exception.sign_in_would_help)

    def test_signing_in_would_not_help_with_other_refusals(self):
        refusal = {'playabilityStatus': {'status': 'UNPLAYABLE'}}
        self.responses = {'ANDROID': refusal, 'ANDROID_VR': refusal}
        with self.assertRaises(innertube.PlayabilityError) as context:
            self.get_player('abc', 'de', 'DE')
        self.assertFalse(context.exception.sign_in_would_help)

    def test_a_substitute_video_is_a_refusal(self):
        self.responses['ANDROID'] = player_response('other')
        player = self.get_player('abc', 'de', 'DE')
        self.assertIs(player.client, innertube.ANDROID_VR)

    def test_the_urls_reporting_playback_come_from_the_signed_in_vr_app(self):
        self.responses['ANDROID_VR'] = dict(player_response('abc'), playbackTracking=TRACKING)
        response = innertube.get_signed_in_player('abc', 'de', 'DE', 'access-vr')
        self.assertEqual(response['playbackTracking'], TRACKING)
        self.assertEqual(self.clients_asked(), ['ANDROID_VR'])
        self.assertEqual(self.requests[0][1]['Authorization'], 'Bearer access-vr')

    def test_a_refused_video_has_no_signed_in_player(self):
        self.responses['ANDROID_VR'] = dict(BOT_CHECK, playbackTracking=TRACKING)
        self.assertIsNone(innertube.get_signed_in_player('abc', 'de', 'DE', 'access-vr'))

    def test_every_playback_gets_a_nonce_of_its_own(self):
        cpn = innertube.new_cpn()
        self.assertRegex(cpn, '^[A-Za-z0-9_-]{16}$')
        self.assertNotEqual(cpn, innertube.new_cpn())


class BrowseTestCase(unittest.TestCase):

    def setUp(self):
        self.requests = []
        self.response = browse_response()
        patcher = mock.patch.object(innertube.http, 'post_json', self._post_json)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post_json(self, url, payload, headers):
        self.requests.append((url, payload, headers))
        return self.response


class ShelvesTest(BrowseTestCase):

    def test_the_feed_is_browsed_as_the_signed_in_vr_app(self):
        innertube.get_shelves(innertube.HISTORY, 'de', 'DE', 'access-vr')
        url, payload, headers = self.requests[0]
        self.assertEqual((url, payload['browseId']), (innertube.BROWSE_URL, 'FEhistory'))
        self.assertEqual(payload['context']['client']['clientName'], 'ANDROID_VR')
        self.assertEqual((payload['context']['client']['hl'],
                          payload['context']['client']['gl']), ('de', 'DE'))
        self.assertEqual(headers['Authorization'], 'Bearer access-vr')

    def test_shelves_come_with_title_and_videos_in_order(self):
        self.response = browse_response(
            {'shelfRenderer': {'title': {'runs': [{'text': 'Empfohlen'}]},
                               'content': {'verticalListRenderer': {'items': [
                                   compact_video('v2'), compact_video('v1')]}}}},
            {'shelfRenderer': {'title': {'simpleText': 'Kürzlich hochgeladen'},
                               'content': {'horizontalListRenderer': {'items': [
                                   compact_video('v3')]}}}})
        self.assertEqual(innertube.get_shelves(innertube.RECOMMENDATIONS, 'de', 'DE', 't'),
                         [innertube.Shelf('Empfohlen', ['v2', 'v1']),
                          innertube.Shelf('Kürzlich hochgeladen', ['v3'])])

    def test_a_section_of_items_is_a_shelf_without_title(self):
        self.response = browse_response(
            {'itemSectionRenderer': {'contents': [compact_video('v1'), compact_video('v2')]}})
        self.assertEqual(innertube.get_shelves(innertube.HISTORY, 'de', 'DE', 't'),
                         [innertube.Shelf('', ['v1', 'v2'])])

    def test_whatever_is_no_video_is_left_out(self):
        self.response = browse_response(
            {'shelfRenderer': {'title': {'simpleText': 'Mixed'},
                               'content': {'verticalListRenderer': {'items': [
                                   {'compactChannelRenderer': {'channelId': 'UC1'}},
                                   compact_video('v1')]}}}},
            {'shelfRenderer': {'title': {'simpleText': 'Channels only'},
                               'content': {'verticalListRenderer': {'items': [
                                   {'compactChannelRenderer': {'channelId': 'UC2'}}]}}}},
            {'continuationItemRenderer': {}})
        self.assertEqual(innertube.get_shelves(innertube.RECOMMENDATIONS, 'de', 'DE', 't'),
                         [innertube.Shelf('Mixed', ['v1'])])

    def test_an_unexpected_response_has_no_shelves(self):
        self.response = {'responseContext': {}}
        self.assertEqual(innertube.get_shelves(innertube.HISTORY, 'de', 'DE', 't'), [])


def watched_video(video_id, percent):
    video = compact_video(video_id)
    video['compactVideoRenderer']['thumbnailOverlays'] = [
        {'thumbnailOverlayTimeStatusRenderer': {'text': {'simpleText': '3:33'}}},
        {'thumbnailOverlayResumePlaybackRenderer': {'percentDurationWatched': percent}}]
    return video


class WatchProgressTest(BrowseTestCase):

    def test_the_history_is_browsed_as_the_signed_in_vr_app(self):
        innertube.get_watch_progress('de', 'DE', 'access-vr')
        url, payload, headers = self.requests[0]
        self.assertEqual((url, payload['browseId']), (innertube.BROWSE_URL, 'FEhistory'))
        self.assertEqual(payload['context']['client']['clientName'], 'ANDROID_VR')
        self.assertEqual(headers['Authorization'], 'Bearer access-vr')

    def test_every_video_comes_with_how_far_it_was_watched(self):
        self.response = browse_response(
            {'itemSectionRenderer': {'contents': [watched_video('v1', 47),
                                                  watched_video('v2', 100)]}},
            {'itemSectionRenderer': {'contents': [watched_video('v3', 5)]}})
        self.assertEqual(innertube.get_watch_progress('de', 'DE', 't'),
                         {'v1': 47, 'v2': 100, 'v3': 5})

    def test_of_a_video_watched_twice_the_latest_viewing_counts(self):
        self.response = browse_response(
            {'itemSectionRenderer': {'contents': [watched_video('v1', 30),
                                                  watched_video('v1', 100)]}})
        self.assertEqual(innertube.get_watch_progress('de', 'DE', 't'), {'v1': 30})

    def test_a_video_without_progress_is_left_out(self):
        self.response = browse_response(
            {'itemSectionRenderer': {'contents': [compact_video('v1'),
                                                  watched_video('v2', 10)]}})
        self.assertEqual(innertube.get_watch_progress('de', 'DE', 't'), {'v2': 10})


def removable_video(video_id, token):
    video = compact_video(video_id)
    video['compactVideoRenderer']['menu'] = {'menuRenderer': {'items': [
        {'menuServiceItemRenderer': {
            'text': {'runs': [{'text': 'Aus Wiedergabeverlauf entfernen'}]},
            'serviceEndpoint': {'feedbackEndpoint': {'feedbackToken': token}}}}]}}
    return video


class RemoveFromHistoryTest(BrowseTestCase):

    def setUp(self):
        super().setUp()
        self.response = browse_response(
            {'itemSectionRenderer': {'contents': [removable_video('v1', 'token-1a'),
                                                  removable_video('v2', 'token-2')]}},
            {'itemSectionRenderer': {'contents': [removable_video('v1', 'token-1b')]}})

    def test_every_viewing_of_the_video_is_removed_as_the_signed_in_vr_app(self):
        self.assertTrue(innertube.remove_from_history('v1', 'de', 'DE', 'access-vr'))
        url, payload, headers = self.requests[1]
        self.assertEqual(url, innertube.FEEDBACK_URL)
        self.assertEqual(payload['feedbackTokens'], ['token-1a', 'token-1b'])
        self.assertEqual(payload['context']['client']['clientName'], 'ANDROID_VR')
        self.assertEqual(headers['Authorization'], 'Bearer access-vr')

    def test_a_video_not_in_the_history_is_left_alone(self):
        self.assertFalse(innertube.remove_from_history('v9', 'de', 'DE', 'access-vr'))
        self.assertEqual(len(self.requests), 1)
