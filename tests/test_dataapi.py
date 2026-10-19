# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.dataapi."""

import calendar
import unittest
from unittest import mock
from urllib.parse import parse_qsl
from urllib.parse import urlsplit

# Importing support installs the xbmc* stubs, so it has to come first.
import tests.support  # noqa: F401

from resources.lib import dataapi


USER = dataapi.Auth('access-user', 'key-1')
KEY_ONLY = dataapi.Auth(None, 'key-1')


def subscription(channel_id, title):
    return {'id': 'sub-' + channel_id,
            'snippet': {'title': title, 'resourceId': {'channelId': channel_id},
                        'thumbnails': {'default': {'url': 'https://yt3/{}-s'.format(channel_id)},
                                       'high': {'url': 'https://yt3/{}-h'.format(channel_id)}}}}


def playlist_item(video_id, published=''):
    return {'contentDetails': {'videoId': video_id, 'videoPublishedAt': published}}


def video(video_id, duration='PT4M13S', **snippet):
    data = {'title': 'Title ' + video_id, 'description': 'About ' + video_id,
            'channelId': 'UCchannel', 'channelTitle': 'Channel',
            'publishedAt': '2026-10-14T16:00:07Z',
            'thumbnails': {'medium': {'url': 'https://i.ytimg.com/{}/mq.jpg'.format(video_id)},
                           'maxres': {'url': 'https://i.ytimg.com/{}/max.jpg'.format(video_id)}}}
    data.update(snippet)
    return {'id': video_id, 'snippet': data, 'contentDetails': {'duration': duration}}


def error(reason, code=403):
    return {'error': {'code': code, 'message': reason, 'errors': [{'reason': reason}]}}


class DataApiTestCase(unittest.TestCase):

    def setUp(self):
        self.requests = []
        self.methods = []
        # Responses by resource, answered from front to back; videos are
        # answered from self.known_videos.
        self.responses = {}
        self.known_videos = {}
        patcher = mock.patch.object(dataapi.http, 'request_json', self._request_json)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _request_json(self, method, url, headers, payload=None):
        parts = urlsplit(url)
        resource = parts.path.rsplit('/', 1)[-1]
        params = dict(parse_qsl(parts.query))
        self.requests.append((resource, params, headers))
        self.methods.append((method, payload))
        if resource == 'videos' and 'id' in params:
            return {'items': [self.known_videos[video_id]
                              for video_id in params['id'].split(',')
                              if video_id in self.known_videos]}
        return self.responses[resource].pop(0)

    def requested(self, resource):
        return [params for name, params, _ in self.requests if name == resource]


class SubscriptionsTest(DataApiTestCase):

    def test_all_pages_are_collected(self):
        self.responses['subscriptions'] = [
            {'items': [subscription('UC1', 'Alpha')], 'nextPageToken': 'p2'},
            {'items': [subscription('UC2', 'Beta')]},
        ]
        channels = dataapi.subscriptions(auth=USER)

        self.assertEqual([(channel.channel_id, channel.title, channel.subscription_id)
                          for channel in channels],
                         [('UC1', 'Alpha', 'sub-UC1'), ('UC2', 'Beta', 'sub-UC2')])
        self.assertEqual([params.get('pageToken') for params in self.requested('subscriptions')],
                         [None, 'p2'])

    def test_the_own_subscriptions_are_asked_for_by_title(self):
        self.responses['subscriptions'] = [{'items': []}]
        dataapi.subscriptions(auth=USER)
        params = self.requested('subscriptions')[0]
        self.assertEqual((params['mine'], params['order'], params['maxResults']),
                         ('true', 'alphabetical', '50'))

    def test_the_account_is_authorized_by_its_token(self):
        self.responses['subscriptions'] = [{'items': []}]
        dataapi.subscriptions(auth=USER)
        self.assertEqual(self.requests[0][2], {'Authorization': 'Bearer access-user'})
        self.assertNotIn('key', self.requests[0][1])

    def test_without_an_account_the_api_key_is_used(self):
        self.responses['videos'] = [{'items': []}]
        dataapi.most_popular('DE', '10', 50, auth=KEY_ONLY)
        self.assertEqual(self.requests[0][2], {})
        self.assertEqual(self.requests[0][1]['key'], 'key-1')

    def test_the_largest_thumbnail_is_taken(self):
        self.responses['subscriptions'] = [{'items': [subscription('UC1', 'Alpha')]}]
        self.assertEqual(dataapi.subscriptions(auth=USER)[0].thumbnail, 'https://yt3/UC1-h')

    def test_a_refusal_carries_the_reason(self):
        self.responses['subscriptions'] = [error('quotaExceeded')]
        with self.assertRaises(dataapi.DataApiError) as context:
            dataapi.subscriptions(auth=USER)
        self.assertEqual(str(context.exception), 'quotaExceeded')


class QuotaResetTest(unittest.TestCase):

    @staticmethod
    def utc(*moment):
        return calendar.timegm(moment + (0,) * (6 - len(moment)))

    def test_it_is_midnight_pacific_standard_time_in_winter(self):
        self.assertEqual(dataapi.quota_reset(self.utc(2026, 1, 15, 20)), self.utc(2026, 1, 16, 8))

    def test_it_is_midnight_pacific_daylight_time_in_summer(self):
        self.assertEqual(dataapi.quota_reset(self.utc(2026, 7, 15, 20)), self.utc(2026, 7, 16, 7))

    def test_at_midnight_itself_the_next_one_is_meant(self):
        self.assertEqual(dataapi.quota_reset(self.utc(2026, 7, 16, 7)), self.utc(2026, 7, 17, 7))

    def test_after_the_switch_to_daylight_saving_time_midnight_is_in_it(self):
        # 1:30 on Sunday, 8 March 2026, still standard time
        self.assertEqual(dataapi.quota_reset(self.utc(2026, 3, 8, 9, 30)), self.utc(2026, 3, 9, 7))

    def test_after_the_switch_to_standard_time_midnight_is_in_it(self):
        # 1:30 on Sunday, 1 November 2026, still daylight saving time
        self.assertEqual(dataapi.quota_reset(self.utc(2026, 11, 1, 8, 30)),
                         self.utc(2026, 11, 2, 8))


class SubscribeTest(DataApiTestCase):

    def test_subscribing_posts_the_channel_and_returns_the_subscription(self):
        self.responses['subscriptions'] = [{'id': 'sub-UC1', 'snippet': {}}]
        self.assertEqual(dataapi.subscribe('UC1', auth=USER), 'sub-UC1')
        self.assertEqual(self.methods, [('POST', {'snippet': {'resourceId': {
            'kind': 'youtube#channel', 'channelId': 'UC1'}}})])
        self.assertEqual(self.requested('subscriptions'), [{'part': 'snippet'}])

    def test_unsubscribing_deletes_the_subscription(self):
        self.responses['subscriptions'] = [{}]
        dataapi.unsubscribe('sub-UC1', auth=USER)
        self.assertEqual(self.methods, [('DELETE', None)])
        self.assertEqual(self.requested('subscriptions'), [{'id': 'sub-UC1'}])

    def test_a_refused_change_is_an_error(self):
        self.responses['subscriptions'] = [error('subscriptionForbidden')]
        with self.assertRaises(dataapi.DataApiError):
            dataapi.subscribe('UC1', auth=USER)


class LikedVideosTest(DataApiTestCase):

    def test_the_videos_rated_like_are_asked_for(self):
        self.responses['videos'] = [{'items': [video('v1'), video('v2')]}]
        videos = dataapi.liked_videos(100, auth=USER)
        self.assertEqual([video.video_id for video in videos], ['v1', 'v2'])
        self.assertEqual(self.requested('videos'), [{
            'part': 'snippet,contentDetails,statistics', 'myRating': 'like', 'maxResults': '50'}])


class RatingTest(DataApiTestCase):

    def test_the_ratings_are_asked_for_fifty_videos_at_a_time(self):
        video_ids = ['v{}'.format(number) for number in range(51)]
        self.responses['getRating'] = [
            {'items': [{'videoId': 'v0', 'rating': 'like'}, {'videoId': 'v1', 'rating': 'none'}]},
            {'items': [{'videoId': 'v50', 'rating': 'dislike'}]}]
        self.assertEqual(dataapi.ratings(video_ids, auth=USER),
                         {'v0': 'like', 'v1': 'none', 'v50': 'dislike'})
        self.assertEqual(self.requested('getRating'),
                         [{'id': ','.join(video_ids[:50])}, {'id': 'v50'}])

    def test_no_videos_ask_for_nothing(self):
        self.assertEqual(dataapi.ratings([], auth=USER), {})
        self.assertEqual(self.requests, [])

    def test_rating_posts_the_video_and_its_rating(self):
        self.responses['rate'] = [{}]
        dataapi.rate('v1', 'like', auth=USER)
        self.assertEqual(self.methods, [('POST', None)])
        self.assertEqual(self.requested('rate'), [{'id': 'v1', 'rating': 'like'}])


class ChannelVideosTest(DataApiTestCase):

    def test_the_videos_tab_playlist_is_read(self):
        self.responses['playlistItems'] = [{'items': []}]
        dataapi.channel_videos('UCabcdef', 100, auth=USER)
        self.assertEqual(self.requested('playlistItems')[0]['playlistId'], 'UULFabcdef')

    def test_the_videos_come_with_details_in_playlist_order(self):
        self.responses['playlistItems'] = [{'items': [playlist_item('v2'), playlist_item('v1')]}]
        self.known_videos = {'v1': video('v1'), 'v2': video('v2')}

        videos = dataapi.channel_videos('UCabc', 100, auth=USER)
        self.assertEqual([video.video_id for video in videos], ['v2', 'v1'])

    def test_no_more_than_asked_for_are_fetched(self):
        self.responses['playlistItems'] = [
            {'items': [playlist_item('v{}'.format(i)) for i in range(50)], 'nextPageToken': 'p2'},
            {'items': [playlist_item('v{}'.format(i)) for i in range(50, 100)],
             'nextPageToken': 'p3'},
        ]
        self.known_videos = {'v{}'.format(i): video('v{}'.format(i)) for i in range(100)}

        videos = dataapi.channel_videos('UCabc', 60, auth=USER)
        self.assertEqual(len(videos), 60)
        self.assertEqual(len(self.requested('playlistItems')), 2)
        self.assertEqual([len(params['id'].split(',')) for params in self.requested('videos')],
                         [50, 10])

    def test_the_uploads_come_with_their_publication(self):
        self.responses['playlistItems'] = [{'items': [playlist_item('v2', '2026-10-18T10:00:00Z'),
                                                      playlist_item('v1', '2026-10-17T10:00:00Z')]}]
        self.assertEqual(dataapi.channel_uploads('UCabc', 50, auth=USER),
                         [('2026-10-18T10:00:00Z', 'v2'), ('2026-10-17T10:00:00Z', 'v1')])
        self.assertEqual(self.requested('videos'), [])

    def test_vanished_videos_are_left_out(self):
        self.responses['playlistItems'] = [{'items': [playlist_item('v1'), playlist_item('gone')]}]
        self.known_videos = {'v1': video('v1')}
        self.assertEqual([video.video_id for video in dataapi.channel_videos('UCabc', 100, USER)],
                         ['v1'])

    def test_a_channel_without_videos_has_none(self):
        self.responses['playlistItems'] = [error('playlistNotFound', code=404)]
        self.assertEqual(dataapi.channel_videos('UCabc', 100, auth=USER), [])

    def test_other_refusals_are_passed_on(self):
        self.responses['playlistItems'] = [error('quotaExceeded')]
        with self.assertRaises(dataapi.DataApiError):
            dataapi.channel_videos('UCabc', 100, auth=USER)


class MostPopularTest(DataApiTestCase):

    def test_the_chart_of_the_regions_category_is_asked_for(self):
        self.responses['videos'] = [{'items': [video('v1'), video('v2')]}]
        videos = dataapi.most_popular('DE', '10', 100, auth=USER)
        self.assertEqual([video.video_id for video in videos], ['v1', 'v2'])
        params = self.requested('videos')[0]
        self.assertEqual((params['chart'], params['regionCode'], params['videoCategoryId']),
                         ('mostPopular', 'DE', '10'))

    def test_a_category_without_chart_is_refused(self):
        self.responses['videos'] = [error('videoChartNotFound', code=404)]
        with self.assertRaises(dataapi.DataApiError) as context:
            dataapi.most_popular('DE', '18', 1, auth=USER)
        self.assertEqual(str(context.exception), 'videoChartNotFound')


class VideoCategoriesTest(DataApiTestCase):

    def test_the_assignable_categories_of_the_region_are_named_in_its_language(self):
        self.responses['videoCategories'] = [{'items': [
            {'id': '1', 'snippet': {'title': 'Film & Animation', 'assignable': True}},
            {'id': '18', 'snippet': {'title': 'Kurzfilme', 'assignable': False}},
            {'id': '10', 'snippet': {'title': 'Musik', 'assignable': True}},
        ]}]
        self.assertEqual(dataapi.video_categories('DE', 'de', auth=USER),
                         [dataapi.Category('1', 'Film & Animation'),
                          dataapi.Category('10', 'Musik')])
        params = self.requested('videoCategories')[0]
        self.assertEqual((params['regionCode'], params['hl']), ('DE', 'de'))


class SearchTest(DataApiTestCase):

    def test_found_videos_come_with_details_in_order_of_relevance(self):
        self.responses['search'] = [{'items': [{'id': {'videoId': 'v2'}},
                                               {'id': {'videoId': 'v1'}}]}]
        self.known_videos = {'v1': video('v1'), 'v2': video('v2')}
        videos = dataapi.search('kodi', 'DE', 'de', 50, auth=USER)
        self.assertEqual([video.video_id for video in videos], ['v2', 'v1'])

    def test_channels_and_playlists_mixed_in_are_skipped(self):
        self.responses['search'] = [{'items': [
            {'id': {'kind': 'youtube#channel', 'channelId': 'UC1'}},
            {'id': {'kind': 'youtube#video', 'videoId': 'v1'}},
            {'id': {'kind': 'youtube#playlist', 'playlistId': 'PL1'}},
        ]}]
        self.known_videos = {'v1': video('v1')}
        videos = dataapi.search('kodi', 'DE', 'de', 50, auth=USER)
        self.assertEqual([video.video_id for video in videos], ['v1'])

    def test_only_videos_are_searched_for_region_and_language(self):
        self.responses['search'] = [{'items': []}]
        dataapi.search('kodi', 'AT', 'de', 50, auth=USER)
        params = self.requested('search')[0]
        self.assertEqual((params['q'], params['type'], params['regionCode'],
                          params['relevanceLanguage']), ('kodi', 'video', 'AT', 'de'))

    def test_one_page_is_enough_for_fifty(self):
        self.responses['search'] = [{'items': [{'id': {'videoId': 'v{}'.format(i)}}
                                               for i in range(50)], 'nextPageToken': 'p2'}]
        dataapi.search('kodi', '', '', 50, auth=USER)
        self.assertEqual(len(self.requested('search')), 1)


class VideoDetailsTest(DataApiTestCase):

    def details(self, item):
        self.known_videos = {item['id']: item}
        return dataapi.videos([item['id']], auth=USER)[0]

    def test_the_metadata_is_taken_over(self):
        details = self.details(video('v1', tags=['a', 'b']))
        self.assertEqual((details.title, details.description, details.channel_id,
                          details.channel_title, details.published, details.thumbnail,
                          details.tags),
                         ('Title v1', 'About v1', 'UCchannel', 'Channel', '2026-10-14T16:00:07Z',
                          'https://i.ytimg.com/v1/max.jpg', ['a', 'b']))

    def test_durations_are_converted_to_seconds(self):
        for duration, seconds in (('PT4M13S', 253), ('PT1H2M3S', 3723), ('PT45S', 45),
                                  ('PT2H', 7200), ('P1DT1S', 86401), ('P0D', 0), ('', 0)):
            self.assertEqual(self.details(video('v1', duration=duration)).duration, seconds,
                             duration)

    def test_missing_fields_do_no_harm(self):
        details = self.details({'id': 'v1', 'snippet': {}})
        self.assertEqual((details.title, details.duration, details.thumbnail, details.tags),
                         ('', 0, '', []))

    def test_the_counts_are_taken_over(self):
        item = dict(video('v1'), statistics={'viewCount': '6340', 'likeCount': '781',
                                             'favoriteCount': '0', 'commentCount': '167'})
        details = self.details(item)
        self.assertEqual((details.views, details.likes), (6340, 781))
        self.assertEqual(self.requested('videos')[0]['part'],
                         'snippet,contentDetails,statistics')

    def test_counts_youtube_hides_are_none(self):
        details = self.details(dict(video('v1'), statistics={'viewCount': '12'}))
        self.assertEqual((details.views, details.likes), (12, None))
