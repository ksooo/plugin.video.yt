# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.dataapi."""

import unittest
from unittest import mock
from urllib.parse import parse_qsl
from urllib.parse import urlsplit

# Importing support installs the xbmc* stubs, so it has to come first.
import tests.support  # noqa: F401

from resources.lib import dataapi


def subscription(channel_id, title):
    return {'id': 'sub-' + channel_id,
            'snippet': {'title': title, 'resourceId': {'channelId': channel_id},
                        'thumbnails': {'default': {'url': 'https://yt3/{}-s'.format(channel_id)},
                                       'high': {'url': 'https://yt3/{}-h'.format(channel_id)}}}}


def playlist_item(video_id):
    return {'contentDetails': {'videoId': video_id}}


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
        if resource == 'videos':
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
        channels = dataapi.subscriptions(token='access-user')

        self.assertEqual([(channel.channel_id, channel.title, channel.subscription_id)
                          for channel in channels],
                         [('UC1', 'Alpha', 'sub-UC1'), ('UC2', 'Beta', 'sub-UC2')])
        self.assertEqual([params.get('pageToken') for params in self.requested('subscriptions')],
                         [None, 'p2'])

    def test_the_own_subscriptions_are_asked_for_by_title(self):
        self.responses['subscriptions'] = [{'items': []}]
        dataapi.subscriptions(token='access-user')
        params = self.requested('subscriptions')[0]
        self.assertEqual((params['mine'], params['order'], params['maxResults']),
                         ('true', 'alphabetical', '50'))

    def test_the_account_is_authorized_by_its_token(self):
        self.responses['subscriptions'] = [{'items': []}]
        dataapi.subscriptions(token='access-user')
        self.assertEqual(self.requests[0][2], {'Authorization': 'Bearer access-user'})

    def test_the_largest_thumbnail_is_taken(self):
        self.responses['subscriptions'] = [{'items': [subscription('UC1', 'Alpha')]}]
        self.assertEqual(dataapi.subscriptions(token='t')[0].thumbnail, 'https://yt3/UC1-h')

    def test_a_refusal_carries_the_reason(self):
        self.responses['subscriptions'] = [error('quotaExceeded')]
        with self.assertRaises(dataapi.DataApiError) as context:
            dataapi.subscriptions(token='t')
        self.assertEqual(str(context.exception), 'quotaExceeded')


class SubscribeTest(DataApiTestCase):

    def test_subscribing_posts_the_channel_and_returns_the_subscription(self):
        self.responses['subscriptions'] = [{'id': 'sub-UC1', 'snippet': {}}]
        self.assertEqual(dataapi.subscribe('UC1', token='t'), 'sub-UC1')
        self.assertEqual(self.methods, [('POST', {'snippet': {'resourceId': {
            'kind': 'youtube#channel', 'channelId': 'UC1'}}})])
        self.assertEqual(self.requested('subscriptions'), [{'part': 'snippet'}])

    def test_unsubscribing_deletes_the_subscription(self):
        self.responses['subscriptions'] = [{}]
        dataapi.unsubscribe('sub-UC1', token='t')
        self.assertEqual(self.methods, [('DELETE', None)])
        self.assertEqual(self.requested('subscriptions'), [{'id': 'sub-UC1'}])

    def test_a_refused_change_is_an_error(self):
        self.responses['subscriptions'] = [error('subscriptionForbidden')]
        with self.assertRaises(dataapi.DataApiError):
            dataapi.subscribe('UC1', token='t')


class ChannelVideosTest(DataApiTestCase):

    def test_the_videos_tab_playlist_is_read(self):
        self.responses['playlistItems'] = [{'items': []}]
        dataapi.channel_videos('UCabcdef', 100, token='t')
        self.assertEqual(self.requested('playlistItems')[0]['playlistId'], 'UULFabcdef')

    def test_the_videos_come_with_details_in_playlist_order(self):
        self.responses['playlistItems'] = [{'items': [playlist_item('v2'), playlist_item('v1')]}]
        self.known_videos = {'v1': video('v1'), 'v2': video('v2')}

        videos = dataapi.channel_videos('UCabc', 100, token='t')
        self.assertEqual([video.video_id for video in videos], ['v2', 'v1'])

    def test_no_more_than_asked_for_are_fetched(self):
        self.responses['playlistItems'] = [
            {'items': [playlist_item('v{}'.format(i)) for i in range(50)], 'nextPageToken': 'p2'},
            {'items': [playlist_item('v{}'.format(i)) for i in range(50, 100)],
             'nextPageToken': 'p3'},
        ]
        self.known_videos = {'v{}'.format(i): video('v{}'.format(i)) for i in range(100)}

        videos = dataapi.channel_videos('UCabc', 60, token='t')
        self.assertEqual(len(videos), 60)
        self.assertEqual(len(self.requested('playlistItems')), 2)
        self.assertEqual([len(params['id'].split(',')) for params in self.requested('videos')],
                         [50, 10])

    def test_vanished_videos_are_left_out(self):
        self.responses['playlistItems'] = [{'items': [playlist_item('v1'), playlist_item('gone')]}]
        self.known_videos = {'v1': video('v1')}
        self.assertEqual([video.video_id for video in dataapi.channel_videos('UCabc', 100, 't')],
                         ['v1'])

    def test_a_channel_without_videos_has_none(self):
        self.responses['playlistItems'] = [error('playlistNotFound', code=404)]
        self.assertEqual(dataapi.channel_videos('UCabc', 100, token='t'), [])

    def test_other_refusals_are_passed_on(self):
        self.responses['playlistItems'] = [error('quotaExceeded')]
        with self.assertRaises(dataapi.DataApiError):
            dataapi.channel_videos('UCabc', 100, token='t')


class VideoDetailsTest(DataApiTestCase):

    def details(self, item):
        self.known_videos = {item['id']: item}
        return dataapi.videos([item['id']], token='t')[0]

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
