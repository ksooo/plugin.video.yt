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

from resources.lib import addon
from resources.lib import dataapi
from resources.lib import http
from resources.lib import innertube
from resources.lib.router import Router

CHANNELS = [dataapi.Channel('UC1', 'Alpha & Omega', 'https://yt3/UC1', 'sub-UC1'),
            dataapi.Channel('UC2', 'Beta', '', 'sub-UC2')]

VIDEO = dataapi.Video(video_id='dQw4w9WgXcQ', title='Never Gonna Give You Up',
                      description='The official video.', channel_id='UC1',
                      channel_title='Alpha & Omega', published='2009-10-25T06:57:33Z',
                      duration=213,
                      thumbnail='https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg',
                      tags=['rick', 'astley'])

SHELVES = [innertube.Shelf('Empfohlen', ['r1', 'r2']),
           innertube.Shelf('Kürzlich hochgeladen', ['r3'])]

SUBSCRIPTIONS_CACHE = os.path.join(support.PROFILE_DIR, 'subscriptions.json')


class BrowseTestCase(AddonTestCase):

    def setUp(self):
        super().setUp()
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        self.queries = []
        # Results of the data API calls by name, and an exception all of them
        # raise instead.
        self.results = {'subscriptions': CHANNELS, 'channel_videos': [VIDEO],
                        'most_popular': [VIDEO], 'search': [VIDEO], 'videos': [VIDEO],
                        'video_categories': [dataapi.Category('10', 'Musik'),
                                             dataapi.Category('20', 'Gaming')],
                        'subscribe': 'sub-new', 'unsubscribe': None}
        self.failure = None
        for name in self.results:
            patcher = mock.patch.object(dataapi, name, self._query(name))
            patcher.start()
            self.addCleanup(patcher.stop)

        self.shelves = {innertube.RECOMMENDATIONS: SHELVES,
                        innertube.HISTORY: [innertube.Shelf('', ['h2', 'h1'])]}
        self.browsed = []
        # How far the videos in the account's history were watched, or an
        # exception asking for it raises.
        self.progress = {}
        for patcher in (mock.patch.object(innertube, 'get_shelves', self._get_shelves),
                        mock.patch.object(innertube, 'get_watch_progress',
                                          self._get_watch_progress)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _get_shelves(self, browse_id, language, region, access_token):
        self.browsed.append((browse_id, access_token))
        return self.shelves[browse_id]

    def _get_watch_progress(self, language, region, access_token):
        self.browsed.append(('progress', access_token))
        if isinstance(self.progress, Exception):
            raise self.progress
        return self.progress

    def _query(self, name):
        def query(*args, auth):
            self.queries.append((name, args, auth.token or 'key:' + auth.api_key))
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


    @staticmethod
    def sign_out(api_key=''):
        support.reset()
        support.SETTINGS['api_key'] = api_key


class RootTest(BrowseTestCase):

    def test_everything_is_offered_when_signed_in(self):
        items = self.dispatch()
        self.assertEqual(self.labels(items), ['L30200', 'L30400', 'L30300', 'L30301', 'L30401'])
        self.assertEqual(self.urls(items), ['plugin://plugin.video.yt/subscriptions/',
                                            'plugin://plugin.video.yt/recommended/',
                                            'plugin://plugin.video.yt/trending/',
                                            'plugin://plugin.video.yt/search/',
                                            'plugin://plugin.video.yt/history/'])

    def test_an_api_key_is_enough_for_trending_and_search(self):
        self.sign_out(api_key='key-1')
        self.assertEqual(self.labels(self.dispatch()), ['L30300', 'L30301'])

    def test_without_either_nothing_is_offered(self):
        self.sign_out()
        self.assertEqual(self.dispatch(), [])
        self.assertTrue(support.PLUGIN_STATE['succeeded'])


class SubscriptionsTest(BrowseTestCase):

    def test_the_channels_are_listed_as_folders(self):
        items = self.dispatch('subscriptions')

        self.assertEqual(self.labels(items), ['Alpha & Omega', 'Beta'])
        self.assertTrue(all(is_folder for _, _, is_folder in items))
        self.assertEqual(self.urls(items)[0], 'plugin://plugin.video.yt/channel/'
                                              '?id=UC1&parent=subscriptions&title=Alpha+%26+Omega')

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

    def channel(self, channel_id='UC1', parent='&parent=subscriptions'):
        return self.dispatch('channel',
                             '?id={}&title=Alpha+%26+Omega{}'.format(channel_id, parent))

    def test_the_videos_come_newest_first_whatever_order_youtube_gives(self):
        self.results['channel_videos'] = [
            VIDEO._replace(video_id='old', published='2024-01-01T10:00:00Z'),
            VIDEO._replace(video_id='new', published='2026-10-01T10:00:00Z'),
            VIDEO._replace(video_id='mid', published='2025-06-01T10:00:00Z')]
        self.assertEqual(self.urls(self.channel()),
                         ['plugin://plugin.video.yt/play/?v=new',
                          'plugin://plugin.video.yt/play/?v=mid',
                          'plugin://plugin.video.yt/play/?v=old'])

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

    def test_the_default_order_shows_the_date_beside_each_video(self):
        self.channel()
        self.assertEqual(support.PLUGIN_STATE['label2_masks']['unsorted'], '%J')

    def test_the_breadcrumb_names_the_channel_below_the_subscriptions(self):
        self.channel()
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30200 / Alpha & Omega')

    def test_the_breadcrumb_names_just_the_channel_when_gone_to(self):
        self.channel(parent='')
        self.assertEqual(support.PLUGIN_STATE['category'], 'Alpha & Omega')

    def test_without_sign_in_it_is_listed_with_the_api_key_and_no_subscribing(self):
        self.sign_out(api_key='key-1')
        list_item = self.channel(parent='')[0][1]
        self.assertEqual(self.queries, [('channel_videos', ('UC1', 100), 'key:key-1')])
        self.assertEqual(list_item.context_menu, [])

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


GO_TO_CHANNEL = (
    'L30204', 'Container.Update(plugin://plugin.video.yt/channel/?id=UC1&title=Alpha+%26+Omega)')


class TrendingTest(BrowseTestCase):

    def category(self):
        return self.dispatch('trending/category', '?id=10&title=Musik')

    def test_all_trends_then_the_categories_are_folders_pictured_by_their_top_video(self):
        items = self.dispatch('trending')
        self.assertEqual(self.labels(items), ['L30310', 'Musik', 'Gaming'])
        self.assertEqual(self.urls(items)[:2],
                         ['plugin://plugin.video.yt/trending/category/?id=&title=L30310',
                          'plugin://plugin.video.yt/trending/category/?id=10&title=Musik'])
        self.assertEqual(items[0][1].art['thumb'], VIDEO.thumbnail)
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30300')

    def test_all_trends_lists_the_most_popular_videos_of_all_categories(self):
        self.dispatch('trending/category', '?id=&title=Alle+Trends')
        self.assertEqual(self.queried('most_popular'), [('US', None, 100)])
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30300 / Alle Trends')

    def test_a_category_lists_its_most_popular_videos_in_kodis_region(self):
        support.INFO_LABELS['System.Locale(iso)'] = 'AT'
        items = self.category()
        self.assertEqual(self.queried('most_popular'), [('AT', '10', 100)])
        self.assertEqual(self.urls(items), ['plugin://plugin.video.yt/play/?v=dQw4w9WgXcQ'])
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30300 / Musik')

    def test_videos_lead_to_their_channel_and_know_the_subscription(self):
        self.cache_channels({'UC1': 'sub-UC1'})
        list_item = self.category()[0][1]
        self.assertEqual([entry[0] for entry in list_item.context_menu], ['L30204', 'L30202'])
        self.assertEqual(list_item.context_menu[0], GO_TO_CHANNEL)

    def test_the_entries_name_the_channel(self):
        self.cache_channels({})
        with mock.patch.object(addon, 'localize', lambda string_id: 'L{} {{0}}'.format(string_id)):
            list_item = self.category()[0][1]
        self.assertEqual([entry[0] for entry in list_item.context_menu],
                         ['L30204 Alpha & Omega', 'L30201 Alpha & Omega'])

    def test_without_sign_in_the_api_key_is_used_and_nobody_subscribes(self):
        self.sign_out(api_key='key-1')
        list_item = self.category()[0][1]
        self.assertEqual(self.queries, [('most_popular', ('US', '10', 100), 'key:key-1')])
        self.assertEqual(list_item.context_menu, [GO_TO_CHANNEL])


class RecommendationsTest(BrowseTestCase):

    def test_the_shelves_are_folders_named_and_pictured_like_on_youtube(self):
        items = self.dispatch('recommended')
        self.assertEqual(self.labels(items), ['Empfohlen', 'Kürzlich hochgeladen'])
        self.assertEqual(self.urls(items)[1], 'plugin://plugin.video.yt/recommended/shelf/'
                                              '?title=K%C3%BCrzlich+hochgeladen')
        self.assertEqual(items[0][1].art['thumb'], 'https://i.ytimg.com/vi/r1/hqdefault.jpg')
        self.assertEqual(self.browsed, [('FEwhat_to_watch', 'access-vr')])

    def test_the_list_of_shelves_is_never_cached_by_kodi(self):
        self.dispatch('recommended')
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30400')
        self.assertFalse(support.PLUGIN_STATE['cacheToDisc'])

    def test_a_shelf_lists_its_videos(self):
        self.dispatch('recommended')
        items = self.dispatch('recommended/shelf', '?title=Empfohlen')
        self.assertEqual(self.queried('videos'), [(['r1', 'r2'],)])
        self.assertEqual(self.labels(items), ['Never Gonna Give You Up'])
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30400 / Empfohlen')

    def test_a_shelf_gone_meanwhile_finds_nothing(self):
        self.dispatch('recommended')
        self.results['videos'] = []
        self.dispatch('recommended/shelf', '?title=Gone')
        self.assertEqual(self.queried('videos'), [([],)])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30107')])


class HistoryTest(BrowseTestCase):

    def test_the_videos_watched_last_are_listed(self):
        items = self.dispatch('history')
        self.assertEqual(self.browsed[0], ('FEhistory', 'access-vr'))
        self.assertEqual(self.queried('videos'), [(['h2', 'h1'],)])
        self.assertEqual(self.labels(items), ['Never Gonna Give You Up'])
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30401')

    def test_without_sign_in_the_user_is_told(self):
        self.sign_out(api_key='key-1')
        self.dispatch('history')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30105')])
        self.assertFalse(support.PLUGIN_STATE['succeeded'])
        self.assertEqual(self.browsed, [])


class SyncTest(BrowseTestCase):

    def setUp(self):
        super().setUp()
        support.SETTINGS['sync_playback'] = True

    def found(self):
        """Search and return the info tag values of the video found."""
        return self.dispatch('search/results', '?q=rick')[0][1].info_tag.values

    def test_a_video_watched_partly_on_youtube_resumes_where_it_was_left(self):
        self.progress = {'dQw4w9WgXcQ': 50}
        values = self.found()
        self.assertEqual(values['Playcount'], 0)
        self.assertEqual(values['ResumePoint'], (106.5, 213))

    def test_from_ninety_percent_on_a_video_counts_as_watched(self):
        self.progress = {'dQw4w9WgXcQ': 90}
        values = self.found()
        self.assertEqual(values['Playcount'], 1)
        self.assertEqual(values['ResumePoint'], (0, 213))

    def test_a_video_not_in_the_history_is_left_to_kodi(self):
        self.progress = {'other': 50}
        values = self.found()
        self.assertNotIn('Playcount', values)
        self.assertNotIn('ResumePoint', values)

    def test_a_channels_videos_follow_the_history_too(self):
        self.progress = {'dQw4w9WgXcQ': 50}
        list_item = self.dispatch('channel', '?id=UC1&title=Alpha')[0][1]
        self.assertEqual(list_item.info_tag.values['ResumePoint'], (106.5, 213))

    def test_the_history_is_asked_as_the_quest_app_and_kept_for_a_while(self):
        self.found()
        self.found()
        self.assertEqual(self.browsed, [('progress', 'access-vr')])

    def test_without_the_setting_kodi_keeps_its_own(self):
        support.SETTINGS['sync_playback'] = False
        self.progress = {'dQw4w9WgXcQ': 50}
        self.assertNotIn('ResumePoint', self.found())
        self.assertEqual(self.browsed, [])

    def test_without_sign_in_kodi_keeps_its_own(self):
        self.sign_out(api_key='key-1')
        self.progress = {'dQw4w9WgXcQ': 50}
        self.assertNotIn('ResumePoint', self.found())
        self.assertEqual(self.browsed, [])

    def test_when_the_history_fails_kodi_keeps_its_own(self):
        self.progress = http.RequestError('timed out from https://www.youtube.com/')
        self.assertNotIn('ResumePoint', self.found())
        self.assertTrue(support.PLUGIN_STATE['succeeded'])
        self.assertEqual(self.errors(),
                         ['[plugin.video.yt] timed out from https://www.youtube.com/'])


class EmojiTest(BrowseTestCase):

    TITLES = {
        '🤯 Home Assistant 2026.10: Deine Dashboard-Karten können jetzt SO VIEL MEHR!':
            'Home Assistant 2026.10: Deine Dashboard-Karten können jetzt SO VIEL MEHR!',
        '✈️ Fernzugriff Home Assistant': 'Fernzugriff Home Assistant',
        '🦸‍♂️🚀  From Zero to Hero': 'From Zero to Hero',
        'DIESE Karte verdient Liebe! ❤️ Die schlauste Raum-Karte':
            'DIESE Karte verdient Liebe! ❤️ Die schlauste Raum-Karte',
        'Dieses Display SIEHT dich – mmWave Radar für 10 €':
            'Dieses Display SIEHT dich – mmWave Radar für 10 €',
        '🚀': '🚀',
    }

    def listed(self, title):
        self.results['most_popular'] = [VIDEO._replace(title=title)]
        list_item = self.dispatch('trending/category', '?id=10&title=Musik')[0][1]
        return list_item.label, list_item.info_tag.values['Title']

    def test_only_emojis_starting_a_title_are_removed(self):
        for title, expected in self.TITLES.items():
            self.assertEqual(self.listed(title), (expected, expected), title)


class SearchTest(BrowseTestCase):

    def test_the_search_offers_a_new_search_and_the_recent_ones(self):
        items = self.dispatch('search')
        self.assertEqual(self.labels(items), ['L30303', 'L30302'])
        self.assertEqual(self.urls(items), ['plugin://plugin.video.yt/search/new/',
                                            'plugin://plugin.video.yt/search/recent/'])

    def test_a_new_search_is_an_action_the_recent_ones_a_folder(self):
        items = self.dispatch('search')
        self.assertEqual([is_folder for _, _, is_folder in items], [False, True])
        self.assertNotIn('IsPlayable', items[0][1].properties)

    def test_a_new_search_shows_its_results_under_a_url_of_their_own(self):
        support.INPUT_ANSWER[0] = '  kodi addon '
        self.act('search/new')
        self.assertEqual(support.BUILTINS, [
            'Container.Update(plugin://plugin.video.yt/search/results/?q=kodi+addon)'])

    def test_a_cancelled_search_goes_nowhere(self):
        self.act('search/new')
        self.assertEqual(support.BUILTINS, [])

    def test_recent_searches_can_be_deleted(self):
        self.dispatch('search/results', '?q=kodi addon')
        list_item = self.dispatch('search/recent')[0][1]
        self.assertEqual(list_item.context_menu, [(
            'L30304', 'RunPlugin(plugin://plugin.video.yt/search/forget/?q=kodi+addon)')])

    def test_deleting_asks_first_and_refreshes(self):
        self.dispatch('search/results', '?q=first')
        self.dispatch('search/results', '?q=second')
        support.reset_output()
        Router([support.BASE_URL + 'search/forget/', '-1', '?q=first']).dispatch()

        self.assertEqual(support.CONFIRMATIONS, [('YouTube', 'L30305')])
        self.assertEqual(support.BUILTINS, ['Container.Refresh'])
        self.assertEqual(self.labels(self.dispatch('search/recent')), ['second'])

    def test_saying_no_keeps_the_search(self):
        self.dispatch('search/results', '?q=first')
        support.CONFIRM_ANSWER[0] = False
        support.reset_output()
        Router([support.BASE_URL + 'search/forget/', '-1', '?q=first']).dispatch()
        self.assertEqual(support.BUILTINS, [])
        self.assertEqual(self.labels(self.dispatch('search/recent')), ['first'])

    def test_finding_nothing_is_reported_and_kodi_stays(self):
        self.results['search'] = []
        self.assertEqual(self.dispatch('search/results', '?q=xyzzy'), [])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30107')])
        self.assertFalse(support.PLUGIN_STATE['succeeded'])

    def act(self, route):
        """Run the plugin as Kodi does for an entry that is neither folder nor playable."""
        support.reset_output()
        Router([support.BASE_URL + route + '/', '-1', '']).dispatch()
        self.assertNotIn('succeeded', support.PLUGIN_STATE)

    def test_results_are_searched_in_kodis_region_and_language(self):
        support.INFO_LABELS['System.Locale(iso)'] = 'AT'
        items = self.dispatch('search/results', '?q=kodi')
        self.assertEqual(self.queried('search'), [('kodi', 'AT', 'de', 50)])
        self.assertEqual(self.labels(items), ['Never Gonna Give You Up'])
        self.assertEqual(support.PLUGIN_STATE['category'], 'L30301 / kodi')

    def test_searching_puts_the_query_on_top_of_the_recent_ones(self):
        self.dispatch('search/results', '?q=first')
        self.dispatch('search/results', '?q=second')
        items = self.dispatch('search/recent')
        self.assertEqual(self.labels(items), ['second', 'first'])
        self.assertEqual(self.urls(items)[0], 'plugin://plugin.video.yt/search/results/?q=second')
        self.assertFalse(support.PLUGIN_STATE['cacheToDisc'])


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
        self.sign_out(api_key='key-1')
        self.dispatch('subscriptions')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30105')])
        self.assertFalse(support.PLUGIN_STATE['succeeded'])

    def test_without_sign_in_nor_api_key_the_user_is_told(self):
        self.sign_out()
        self.dispatch('trending')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30106')])
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
