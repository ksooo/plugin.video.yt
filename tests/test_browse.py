# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for the listings and their context menus, driving the add-on as Kodi would."""

import json
import os
import time
from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase
from tests.support import tokens

from resources.lib import dataapi
from resources.lib import http
from resources.lib import listing
from resources.lib.router import Router

CHANNELS = [dataapi.Channel('UC1', 'Alpha & Omega', 'https://yt3/UC1', 'sub-UC1'),
            dataapi.Channel('UC2', 'Beta', '', 'sub-UC2')]

VIDEO = dataapi.Video(video_id='dQw4w9WgXcQ', title='Never Gonna Give You Up',
                      description='The official video.', channel_id='UC1',
                      channel_title='Alpha & Omega', published='2009-10-25T06:57:33Z',
                      duration=213,
                      thumbnail='https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg',
                      tags=['rick', 'astley'])

SUBSCRIPTIONS_CACHE = os.path.join(support.PROFILE_DIR, 'subscriptions.json')


class BrowseTestCase(AddonTestCase):

    def setUp(self):
        super().setUp()
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        self.queries = []
        # Results of the data API calls by name, and an exception all of them
        # raise instead.
        self.results = {'subscriptions': CHANNELS, 'channel_videos': [VIDEO],
                        'subscribe': 'sub-new', 'unsubscribe': None}
        self.failure = None
        for name in self.results:
            patcher = mock.patch.object(dataapi, name, self._query(name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def _query(self, name):
        def query(*args, token):
            self.queries.append((name, args, token))
            if self.failure is not None:
                raise self.failure
            return self.results[name]
        return query

    def queried(self, name):
        return [args for query, args, _ in self.queries if query == name]

    @staticmethod
    def cache_channels(ids, age=0):
        os.makedirs(support.PROFILE_DIR, exist_ok=True)
        with open(SUBSCRIPTIONS_CACHE, 'w', encoding='utf-8') as cache_file:
            json.dump({'saved_at': time.time() - age, 'channels': ids}, cache_file)

    @staticmethod
    def cached_channels():
        with open(SUBSCRIPTIONS_CACHE, encoding='utf-8') as cache_file:
            return json.load(cache_file)['channels']

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
        items = self.dispatch('subscriptions')

        self.assertEqual(self.labels(items), ['Alpha & Omega', 'Beta'])
        self.assertTrue(all(is_folder for _, _, is_folder in items))
        self.assertEqual(self.urls(items)[0],
                         'plugin://plugin.video.yt/channel/?id=UC1&title=Alpha+%26+Omega')

    def test_they_are_asked_for_with_the_users_token(self):
        self.dispatch('subscriptions')
        self.assertEqual(self.queries, [('subscriptions', (), 'access-user')])

    def test_they_are_always_fresh_and_update_the_cache(self):
        self.cache_channels({'UCold': 'sub-old'})
        self.dispatch('subscriptions')
        self.assertEqual(self.cached_channels(), {'UC1': 'sub-UC1', 'UC2': 'sub-UC2'})

    def test_channels_show_their_picture(self):
        items = self.dispatch('subscriptions')
        self.assertEqual(items[0][1].art['thumb'], 'https://yt3/UC1')
        self.assertEqual(items[1][1].art, {'icon': 'DefaultFolder.png'})

    def test_channels_can_be_unsubscribed_from(self):
        items = self.dispatch('subscriptions')
        self.assertEqual(items[0][1].context_menu, [(
            'L30203',
            'RunPlugin(plugin://plugin.video.yt/unsubscribe/?channel=UC1&title=Alpha+%26+Omega)')])

    def test_the_breadcrumb_names_the_folder(self):
        self.dispatch('subscriptions')
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30200')

    def test_kodi_does_not_cache_the_listing(self):
        self.dispatch('subscriptions')
        self.assertFalse(support.PLUGIN_STATE['cacheToDisc'])


class ChannelTest(BrowseTestCase):

    def channel(self, channel_id='UC1'):
        return self.dispatch('channel', '?id={}&title=Alpha+%26+Omega'.format(channel_id))

    def test_the_newest_hundred_videos_of_the_channel_are_asked_for(self):
        self.channel()
        self.assertEqual(self.queried('channel_videos'), [('UC1', 100)])

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
            'Studios': ['Alpha & Omega'],
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

    def test_a_subscribed_channels_videos_offer_unsubscribing_only(self):
        self.cache_channels({'UC1': 'sub-UC1'})
        list_item = self.channel()[0][1]
        self.assertEqual(list_item.context_menu, [(
            'L30202',
            'RunPlugin(plugin://plugin.video.yt/unsubscribe/?channel=UC1&title=Alpha+%26+Omega)')])

    def test_another_channels_videos_offer_subscribing(self):
        self.cache_channels({'UC2': 'sub-UC2'})
        list_item = self.channel()[0][1]
        self.assertEqual(list_item.context_menu, [(
            'L30201',
            'RunPlugin(plugin://plugin.video.yt/subscribe/?channel=UC1&title=Alpha+%26+Omega)')])

    def test_a_recent_cache_spares_asking_for_the_subscriptions(self):
        self.cache_channels({'UC1': 'sub-UC1'}, age=3500)
        self.channel()
        self.assertEqual(self.queried('subscriptions'), [])

    def test_an_old_cache_is_renewed(self):
        self.cache_channels({'UC1': 'sub-UC1'}, age=3700)
        self.channel()
        self.assertEqual(self.queried('subscriptions'), [()])
        self.assertEqual(self.cached_channels(), {'UC1': 'sub-UC1', 'UC2': 'sub-UC2'})


class VideoContextMenuTest(BrowseTestCase):

    def test_videos_elsewhere_lead_to_their_channel(self):
        _, list_item, _ = listing.video_item(VIDEO, subscribed=True, link_channel=True)
        self.assertEqual(list_item.context_menu[0], (
            'L30204',
            'Container.Update(plugin://plugin.video.yt/channel/?id=UC1&title=Alpha+%26+Omega)'))


class SubscriptionChangeTest(BrowseTestCase):

    def act(self, route, channel_id='UC9'):
        support.reset_output()
        Router([support.BASE_URL + route + '/', '-1',
                '?channel={}&title=Gamma'.format(channel_id)]).dispatch()

    def test_subscribing_adds_the_channel_to_the_cache(self):
        self.cache_channels({'UC1': 'sub-UC1'})
        self.act('subscribe')
        self.assertEqual(self.queried('subscribe'), [('UC9',)])
        self.assertEqual(self.cached_channels(), {'UC1': 'sub-UC1', 'UC9': 'sub-new'})

    def test_unsubscribing_ends_the_subscription_and_drops_it_from_the_cache(self):
        self.cache_channels({'UC1': 'sub-UC1', 'UC9': 'sub-UC9'})
        self.act('unsubscribe')
        self.assertEqual(self.queried('unsubscribe'), [('sub-UC9',)])
        self.assertEqual(self.cached_channels(), {'UC1': 'sub-UC1'})

    def test_unsubscribing_asks_first(self):
        self.cache_channels({'UC9': 'sub-UC9'})
        self.act('unsubscribe')
        self.assertEqual(support.CONFIRMATIONS, [('YouTube', 'L30212')])

    def test_saying_no_keeps_the_subscription(self):
        self.cache_channels({'UC9': 'sub-UC9'})
        support.CONFIRM_ANSWER[0] = False
        self.act('unsubscribe')
        self.assertEqual(self.queried('unsubscribe'), [])
        self.assertEqual(self.cached_channels(), {'UC9': 'sub-UC9'})
        self.assertEqual((support.NOTIFICATIONS, support.BUILTINS), ([], []))

    def test_subscribing_does_not_ask(self):
        self.cache_channels({})
        self.act('subscribe')
        self.assertEqual(support.CONFIRMATIONS, [])

    def test_a_subscription_made_elsewhere_is_found_to_end_it(self):
        self.cache_channels({'UC9': 'sub-UC9'})
        self.act('unsubscribe', 'UC2')
        self.assertEqual(self.queried('unsubscribe'), [('sub-UC2',)])

    def test_subscribing_is_reported_and_the_listing_refreshed(self):
        self.cache_channels({})
        self.act('subscribe')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30210')])
        self.assertEqual(support.BUILTINS, ['Container.Refresh'])

    def test_unsubscribing_elsewhere_refreshes_the_listing(self):
        self.cache_channels({'UC9': 'sub-UC9'})
        support.INFO_LABELS['Container.FolderPath'] = 'plugin://plugin.video.yt/subscriptions/'
        self.act('unsubscribe')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30211')])
        self.assertEqual(support.BUILTINS, ['Container.Refresh'])

    def test_unsubscribing_in_the_channels_listing_leaves_it(self):
        self.cache_channels({'UC9': 'sub-UC9'})
        support.INFO_LABELS['Container.FolderPath'] = (
            'plugin://plugin.video.yt/channel/?id=UC9&title=Gamma')
        self.act('unsubscribe')
        self.assertEqual(support.BUILTINS, ['Action(ParentDir)'])

    def test_unsubscribing_in_another_channels_listing_stays(self):
        self.cache_channels({'UC9': 'sub-UC9'})
        support.INFO_LABELS['Container.FolderPath'] = (
            'plugin://plugin.video.yt/channel/?id=UC1&title=Alpha')
        self.act('unsubscribe')
        self.assertEqual(support.BUILTINS, ['Container.Refresh'])

    def test_a_failed_change_is_reported_without_refreshing(self):
        self.cache_channels({})
        self.failure = dataapi.DataApiError('forbidden')
        self.act('subscribe')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30103')])
        self.assertEqual(support.BUILTINS, [])
        self.assertNotIn('succeeded', support.PLUGIN_STATE)


class FailureTest(BrowseTestCase):

    def test_without_sign_in_the_user_is_told(self):
        support.reset()
        self.dispatch('subscriptions')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30105')])
        self.assertFalse(support.PLUGIN_STATE['succeeded'])

    def test_a_used_up_quota_is_named(self):
        self.failure = dataapi.DataApiError('quotaExceeded')
        self.dispatch('subscriptions')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30104')])
        self.assertFalse(support.PLUGIN_STATE['succeeded'])

    def test_other_refusals_are_reported_and_logged(self):
        self.failure = dataapi.DataApiError('forbidden')
        self.dispatch('channel', '?id=UC1&title=x')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30103')])
        self.assertEqual(self.errors(), ['[plugin.video.yt] YouTube Data API: forbidden'])

    def test_a_network_failure_is_reported(self):
        self.failure = http.RequestError('timed out')
        self.dispatch('subscriptions')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30101')])
