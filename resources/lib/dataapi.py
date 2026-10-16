# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The YouTube Data API v3, the official API for everything but playback.

Every call costs quota, 10,000 units a day per Google Cloud project. The
functions note what they cost.
"""

import collections
import re
from urllib.parse import urlencode

from . import http

API_URL = 'https://www.googleapis.com/youtube/v3/'

#: The most items the API returns per request.
PAGE_SIZE = 50

#: How a request is authorized: by the access token of a signed-in account,
#: or else by an API key. Whatever concerns the account itself needs the token.
Auth = collections.namedtuple('Auth', 'token api_key')

#: A subscribed channel. Unsubscribing takes the subscription's id, not the channel's.
Channel = collections.namedtuple('Channel', 'channel_id title thumbnail subscription_id')

Category = collections.namedtuple('Category', 'category_id title')

Video = collections.namedtuple(
    'Video',
    'video_id title description channel_id channel_title published duration thumbnail tags')

_THUMBNAIL_SIZES = ('maxres', 'standard', 'high', 'medium', 'default')

_DURATION = re.compile(r'^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$')


class DataApiError(Exception):
    """The API refused. The message is its reason, e.g. 'quotaExceeded'."""


def subscriptions(auth):
    """Return the channels the account subscribed to, by title. 1 unit per 50 channels."""
    channels = []
    for item in _all_items('subscriptions', {
            'part': 'snippet',
            'mine': 'true',
            'order': 'alphabetical',
    }, auth):
        snippet = item['snippet']
        channels.append(Channel(snippet['resourceId']['channelId'], snippet['title'],
                                _thumbnail(snippet), item['id']))
    return channels


def subscribe(channel_id, auth):
    """Subscribe to the channel and return the subscription's id. 50 units."""
    return _request('POST', 'subscriptions', {'part': 'snippet'}, auth, {
        'snippet': {'resourceId': {'kind': 'youtube#channel', 'channelId': channel_id}},
    })['id']


def unsubscribe(subscription_id, auth):
    """End the subscription. 50 units."""
    _request('DELETE', 'subscriptions', {'id': subscription_id}, auth)


def channel_videos(channel_id, count, auth):
    """Return the newest videos of the channel, newest first. 2 units per 50 videos.

    These are the videos of the channel page's "Videos" tab: no shorts, no
    live recordings. YouTube keeps them in a playlist of their own, whose id
    is derived from the channel id.
    """
    playlist_id = 'UULF' + channel_id[2:]
    video_ids = []
    try:
        for item in _all_items('playlistItems', {
                'part': 'contentDetails',
                'playlistId': playlist_id,
        }, auth, limit=count):
            video_ids.append(item['contentDetails']['videoId'])
    except DataApiError as error:
        # The playlist only exists once the channel has a video in it.
        if str(error) == 'playlistNotFound':
            return []
        raise

    return videos(video_ids, auth)


def video_categories(region, language, auth):
    """Return the categories videos of the region can be put into. 1 unit.

    region and language are ISO codes such as 'DE' and 'de'; language names
    the categories.
    """
    response = _request('GET', 'videoCategories',
                        {'part': 'snippet', 'regionCode': region, 'hl': language}, auth)
    return [Category(item['id'], item['snippet']['title'])
            for item in response.get('items', []) if item['snippet'].get('assignable')]


def most_popular(region, category_id, count, auth):
    """Return the most popular videos, most popular first. 1 unit per 50.

    region is an ISO 3166 code such as 'DE'. category_id narrows them to a
    category, None means all. YouTube has no chart for every category of a
    region; asking for one anyway is refused with 'notFound' or
    'videoChartNotFound'.
    """
    params = {'part': 'snippet,contentDetails', 'chart': 'mostPopular', 'regionCode': region}
    if category_id:
        params['videoCategoryId'] = category_id
    return [_video(item) for item in _all_items('videos', params, auth, limit=count)]


def search(query, region, language, count, auth):
    """Return the videos YouTube finds most relevant for the query. 101 units per 50.

    region and language are ISO codes such as 'DE' and 'de'; either may be empty.
    """
    params = {'part': 'id', 'type': 'video', 'q': query}
    if region:
        params['regionCode'] = region
    if language:
        params['relevanceLanguage'] = language
    # Even searching for videos only, YouTube mixes in the odd channel or playlist.
    video_ids = [item['id']['videoId']
                 for item in _all_items('search', params, auth, limit=count)
                 if 'videoId' in item.get('id', {})]
    return videos(video_ids, auth)


def videos(video_ids, auth):
    """Return the details of the videos in the given order. 1 unit per 50 videos.

    Videos that are private or deleted by now are left out.
    """
    details = {}
    for start in range(0, len(video_ids), PAGE_SIZE):
        response = _request('GET', 'videos', {
            'part': 'snippet,contentDetails',
            'id': ','.join(video_ids[start:start + PAGE_SIZE]),
            'maxResults': PAGE_SIZE,
        }, auth)
        for item in response.get('items', []):
            details[item['id']] = _video(item)
    return [details[video_id] for video_id in video_ids if video_id in details]


def _all_items(resource, params, auth, limit=None):
    """Yield the items of all pages, at most limit of them."""
    count = 0
    page_token = None
    while True:
        page_params = dict(params, maxResults=PAGE_SIZE)
        if page_token:
            page_params['pageToken'] = page_token
        response = _request('GET', resource, page_params, auth)

        for item in response.get('items', []):
            if limit is not None and count >= limit:
                return
            count += 1
            yield item

        page_token = response.get('nextPageToken')
        if not page_token or (limit is not None and count >= limit):
            return


def _request(method, resource, params, auth, payload=None):
    headers = {}
    if auth.token:
        headers['Authorization'] = 'Bearer ' + auth.token
    else:
        params = dict(params, key=auth.api_key)
    response = http.request_json(method, '{}{}?{}'.format(API_URL, resource, urlencode(params)),
                                 headers, payload)
    error = response.get('error')
    if error is not None:
        errors = error.get('errors') or [{}]
        raise DataApiError(errors[0].get('reason') or error.get('status', 'unknown'))
    return response


def _video(item):
    snippet = item['snippet']
    return Video(
        video_id=item['id'],
        title=snippet.get('title', ''),
        description=snippet.get('description', ''),
        channel_id=snippet.get('channelId', ''),
        channel_title=snippet.get('channelTitle', ''),
        published=snippet.get('publishedAt', ''),
        duration=_seconds(item.get('contentDetails', {}).get('duration', '')),
        thumbnail=_thumbnail(snippet),
        tags=snippet.get('tags', []))


def _thumbnail(snippet):
    thumbnails = snippet.get('thumbnails', {})
    for size in _THUMBNAIL_SIZES:
        if size in thumbnails:
            return thumbnails[size]['url']
    return ''


def _seconds(duration):
    """Convert an ISO 8601 duration such as 'PT1H2M3S' to seconds."""
    match = _DURATION.match(duration)
    if match is None:
        return 0
    days, hours, minutes, seconds = (int(value or 0) for value in match.groups())
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds
