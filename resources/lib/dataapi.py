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

from concurrent.futures import ThreadPoolExecutor
import calendar
import collections
import re
import time
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

#: views and likes are None where YouTube hides them, and for videos cached
#: before the add-on knew them.
Video = collections.namedtuple(
    'Video',
    'video_id title description channel_id channel_title published duration thumbnail tags '
    'views likes',
    defaults=(None, None))

#: The parts of a video the listings show. Asking for more costs no more.
_VIDEO_PARTS = 'snippet,contentDetails,statistics'

_THUMBNAIL_SIZES = ('maxres', 'standard', 'high', 'medium', 'default')

_DURATION = re.compile(r'^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$')


class DataApiError(Exception):
    """The API refused. The message is its reason, e.g. 'quotaExceeded'."""


def quota_reset(now):
    """Return when the daily quota starts anew after the Unix time now: at midnight Pacific Time."""
    offset = _pacific_offset(now)
    midnight = (now + offset) // 86400 * 86400 + 86400
    return midnight - _pacific_offset(midnight - offset)


def _pacific_offset(moment):
    """Return the offset of Pacific Time from UTC at the Unix time, in seconds.

    Daylight saving time runs from the second Sunday in March to the first one
    in November, from 2:00 local time on.
    """
    year = time.gmtime(moment).tm_year
    starts = _sunday(year, 3, 2) + 10 * 3600
    ends = _sunday(year, 11, 1) + 9 * 3600
    return (-7 if starts <= moment < ends else -8) * 3600


def _sunday(year, month, number):
    """Return the Unix time of the start, in UTC, of the month's Sunday with the number."""
    first = calendar.timegm((year, month, 1, 0, 0, 0))
    return first + ((6 - time.gmtime(first).tm_wday) % 7 + 7 * (number - 1)) * 86400


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
    """Return the newest videos of the channel, newest first. 2 units per 50 videos."""
    return videos([video_id for _, video_id in channel_uploads(channel_id, count, auth)], auth)


def channel_uploads(channel_id, count, auth):
    """Return (published, video id) of the newest videos of the channel, newest first.

    1 unit per 50. These are the videos of the channel page's "Videos" tab: no
    shorts, no live recordings. YouTube keeps them in a playlist of their own,
    whose id is derived from the channel id.
    """
    playlist_id = 'UULF' + channel_id[2:]
    uploads = []
    try:
        for item in _all_items('playlistItems', {
                'part': 'contentDetails',
                'playlistId': playlist_id,
        }, auth, limit=count):
            details = item['contentDetails']
            uploads.append((details.get('videoPublishedAt', ''), details['videoId']))
    except DataApiError as error:
        # The playlist only exists once the channel has a video in it.
        if str(error) == 'playlistNotFound':
            return []
        raise
    return uploads


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
    params = {'part': _VIDEO_PARTS, 'chart': 'mostPopular', 'regionCode': region}
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
    for response in _per_page(video_ids, lambda page: _request('GET', 'videos', {
            'part': _VIDEO_PARTS,
            'id': ','.join(page),
            'maxResults': PAGE_SIZE,
    }, auth)):
        for item in response.get('items', []):
            details[item['id']] = _video(item)
    return [details[video_id] for video_id in video_ids if video_id in details]


def liked_videos(count, auth):
    """Return the videos the account liked, in YouTube's order. 1 unit per 50."""
    return [_video(item) for item in _all_items('videos', {
        'part': _VIDEO_PARTS,
        'myRating': 'like',
    }, auth, limit=count)]


def ratings(video_ids, auth):
    """Return the account's ratings of the videos by id. 1 unit per 50 videos.

    A rating is 'like', 'dislike' or 'none'.
    """
    result = {}
    for response in _per_page(video_ids, lambda page: _request(
            'GET', 'videos/getRating', {'id': ','.join(page)}, auth)):
        result.update((item['videoId'], item['rating']) for item in response.get('items', []))
    return result


def rate(video_id, rating, auth):
    """Rate the video 'like' or 'dislike', or take the rating back with 'none'. 50 units."""
    _request('POST', 'videos/rate', {'id': video_id, 'rating': rating}, auth)


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


def _per_page(video_ids, request):
    """Return request(page) for the video ids PAGE_SIZE at a time, all asked for at once."""
    pages = [video_ids[start:start + PAGE_SIZE] for start in range(0, len(video_ids), PAGE_SIZE)]
    if not pages:
        return []
    with ThreadPoolExecutor(len(pages)) as pool:
        return list(pool.map(request, pages))


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
    statistics = item.get('statistics', {})
    return Video(
        video_id=item['id'],
        title=snippet.get('title', ''),
        description=snippet.get('description', ''),
        channel_id=snippet.get('channelId', ''),
        channel_title=snippet.get('channelTitle', ''),
        published=snippet.get('publishedAt', ''),
        duration=_seconds(item.get('contentDetails', {}).get('duration', '')),
        thumbnail=_thumbnail(snippet),
        tags=snippet.get('tags', []),
        views=_count(statistics, 'viewCount'),
        likes=_count(statistics, 'likeCount'))


def _count(statistics, name):
    """Return one of a video's counts, None if YouTube hides it."""
    value = statistics.get(name)
    return None if value is None else int(value)


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
