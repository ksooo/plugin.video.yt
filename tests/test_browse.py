# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for the listings, driving the add-on as Kodi would."""

from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase
from tests.support import tokens

from resources.lib import dataapi
from resources.lib import http

CHANNELS = [dataapi.Channel('UC1', 'Alpha & Omega', 'https://yt3/UC1'),
            dataapi.Channel('UC2', 'Beta', '')]

VIDEO = dataapi.Video(video_id='dQw4w9WgXcQ', title='Never Gonna Give You Up',
                      description='The official video.', channel_title='Rick Astley',
                      published='2009-10-25T06:57:33Z', duration=213,
                      thumbnail='https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg',
                      tags=['rick', 'astley'])


class BrowseTestCase(AddonTestCase):

    def setUp(self):
        super().setUp()
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        self.queries = []
        self.result = None
        for name in ('subscriptions', 'channel_videos'):
            patcher = mock.patch.object(dataapi, name, self._query(name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def _query(self, name):
        def query(*args, token):
            self.queries.append((name, args, token))
            if isinstance(self.result, Exception):
                raise self.result
            return self.result
        return query

    @staticmethod
    def urls(items):
        return [url for url, _, _ in items]

    @staticmethod
    def labels(items):
        return [list_item.label for _, list_item, _ in items]


class RootTest(BrowseTestCase):

    def test_subscriptions_are_offered_when_signed_in(self):
        items = self.dispatch()
        self.assertEqual(self.labels(items), ['L30200'])
        self.assertEqual(self.urls(items), ['plugin://plugin.video.yt/subscriptions/'])

    def test_nothing_needing_a_sign_in_is_offered_without(self):
        support.reset()
        self.assertEqual(self.dispatch(), [])
        self.assertTrue(support.PLUGIN_STATE['succeeded'])


class SubscriptionsTest(BrowseTestCase):

    def test_the_channels_are_listed_as_folders(self):
        self.result = CHANNELS
        items = self.dispatch('subscriptions')

        self.assertEqual(self.labels(items), ['Alpha & Omega', 'Beta'])
        self.assertTrue(all(is_folder for _, _, is_folder in items))
        self.assertEqual(self.urls(items)[0],
                         'plugin://plugin.video.yt/channel/?id=UC1&title=Alpha+%26+Omega')

    def test_they_are_asked_for_with_the_users_token(self):
        self.result = CHANNELS
        self.dispatch('subscriptions')
        self.assertEqual(self.queries, [('subscriptions', (), 'access-user')])

    def test_channels_show_their_picture(self):
        self.result = CHANNELS
        items = self.dispatch('subscriptions')
        self.assertEqual(items[0][1].art['thumb'], 'https://yt3/UC1')
        self.assertEqual(items[1][1].art, {'icon': 'DefaultFolder.png'})

    def test_the_breadcrumb_names_the_folder(self):
        self.result = CHANNELS
        self.dispatch('subscriptions')
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30200')


class ChannelTest(BrowseTestCase):

    def setUp(self):
        super().setUp()
        self.result = [VIDEO]

    def channel(self):
        return self.dispatch('channel', '?id=UC1&title=Alpha+%26+Omega')

    def test_the_newest_hundred_videos_of_the_channel_are_asked_for(self):
        self.channel()
        self.assertEqual(self.queries, [('channel_videos', ('UC1', 100), 'access-user')])

    def test_videos_are_playable_under_a_stable_url(self):
        url, list_item, is_folder = self.channel()[0]
        self.assertEqual(url, 'plugin://plugin.video.yt/play/?v=dQw4w9WgXcQ')
        self.assertFalse(is_folder)
        self.assertEqual(list_item.properties['IsPlayable'], 'true')

    def test_videos_carry_their_metadata(self):
        list_item = self.channel()[0][1]
        self.assertEqual(list_item.info_tag.values, {
            'MediaType': 'video',
            'Title': 'Never Gonna Give You Up',
            'Plot': 'The official video.',
            'Studios': ['Rick Astley'],
            'Premiered': '2009-10-25',
            'Duration': 213,
            'Tags': ['rick', 'astley'],
            'UniqueIDs': ({'youtube': 'dQw4w9WgXcQ'}, 'youtube'),
        })
        self.assertEqual(list_item.date_time, '2009-10-25T06:57:33Z')
        self.assertEqual(list_item.art['thumb'], VIDEO.thumbnail)

    def test_kodi_is_left_to_fill_in_play_count_and_resume_point(self):
        list_item = self.channel()[0][1]
        self.assertNotIn('Playcount', list_item.info_tag.values)
        self.assertNotIn('ResumePoint', list_item.info_tag.values)

    def test_the_listing_is_one_of_videos_sorted_newest_first(self):
        self.channel()
        self.assertEqual(support.PLUGIN_STATE['content'], 'videos')
        self.assertEqual(support.PLUGIN_STATE['sort_methods'],
                         ['unsorted', 'date', 'title', 'duration'])

    def test_the_breadcrumb_names_the_channel(self):
        self.channel()
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30200 / Alpha & Omega')


class FailureTest(BrowseTestCase):

    def test_without_sign_in_the_user_is_told(self):
        support.reset()
        self.dispatch('subscriptions')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30105')])
        self.assertFalse(support.PLUGIN_STATE['succeeded'])

    def test_a_used_up_quota_is_named(self):
        self.result = dataapi.DataApiError('quotaExceeded')
        self.dispatch('subscriptions')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30104')])
        self.assertFalse(support.PLUGIN_STATE['succeeded'])

    def test_other_refusals_are_reported_and_logged(self):
        self.result = dataapi.DataApiError('forbidden')
        self.dispatch('channel', '?id=UC1&title=x')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30103')])
        self.assertEqual(self.errors(), ['[plugin.video.yt] YouTube Data API: forbidden'])

    def test_a_network_failure_is_reported(self):
        self.result = http.RequestError('timed out')
        self.dispatch('subscriptions')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30101')])
