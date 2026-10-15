# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""InnerTube, the undocumented API of YouTube's own apps.

Only used for what the YouTube Data API does not offer. For playback the
add-on poses as one of YouTube's apps whose stream URLs need neither a PO
token nor a deciphered n parameter. YouTube retires old app versions, so the
client versions need an update from time to time.
"""

import collections
import random
import string

from . import http

PLAYER_URL = 'https://www.youtube.com/youtubei/v1/player?prettyPrint=false'


class Client:
    """The identity of one of YouTube's apps."""

    def __init__(self, client_id, context, user_agent, origin, params=None):
        self.client_id = client_id
        self.context = context
        self.params = params
        #: Headers for fetching streams and manifests, matching the identity.
        self.stream_headers = {'User-Agent': user_agent, 'Origin': origin}

    @property
    def name(self):
        return self.context['clientName']

    @property
    def api_headers(self):
        return dict(self.stream_headers, **{
            'X-YouTube-Client-Name': self.client_id,
            'X-YouTube-Client-Version': self.context['clientVersion'],
        })


#: The Android app. Without these params it needs a PO token.
ANDROID = Client(
    '3',
    {
        'clientName': 'ANDROID',
        'clientVersion': '20.10.38',
        'osName': 'Android',
        'osVersion': '15',
        'androidSdkVersion': '32',
        'platform': 'MOBILE',
    },
    'com.google.android.youtube/20.10.38 (Linux; U; Android 15) gzip',
    'https://m.youtube.com',
    params='2AMB')

#: The app for Meta Quest. Offers the original audio track only.
ANDROID_VR = Client(
    '28',
    {
        'clientName': 'ANDROID_VR',
        'clientVersion': '1.65.10',
        'deviceMake': 'Oculus',
        'deviceModel': 'Quest 3',
        'osName': 'Android',
        'osVersion': '14',
        'androidSdkVersion': '34',
    },
    'com.google.android.apps.youtube.vr.oculus/1.65.10 '
    '(Linux; U; Android 14; eureka-user Build/UP1A.231005.007.A1) gzip',
    'https://www.youtube.com')

#: Player clients by preference.
PLAYER_CLIENTS = (ANDROID, ANDROID_VR)

#: A player response and the client it was given to.
Player = collections.namedtuple('Player', 'response client')

_CPN_ALPHABET = string.ascii_letters + string.digits + '-_'


class PlayabilityError(Exception):
    """YouTube refuses to play the video. The message is YouTube's reason, if it gave one."""


def get_player(video_id, language, region):
    """Return the player response of the first client YouTube serves the video to.

    language and region are ISO codes such as 'de' and 'DE'; YouTube words its
    reasons for refusing a video in that language. Either may be empty.
    """
    reasons = []
    for client in PLAYER_CLIENTS:
        response = _request_player(client, video_id, language, region)
        if not _is_playable(response, video_id):
            # Refusals such as YouTube's bot check carry a visitor id that
            # passes it.
            visitor_data = response.get('responseContext', {}).get('visitorData')
            if visitor_data:
                response = _request_player(client, video_id, language, region, visitor_data)

        if _is_playable(response, video_id):
            return Player(response, client)

        reasons.append(response.get('playabilityStatus', {}).get('reason', ''))

    raise PlayabilityError(next((reason for reason in reasons if reason), ''))


def _request_player(client, video_id, language, region, visitor_data=None):
    context = dict(client.context)
    headers = client.api_headers
    if language:
        context['hl'] = language
    if region:
        context['gl'] = region
    if visitor_data:
        context['visitorData'] = visitor_data
        headers['X-Goog-Visitor-Id'] = visitor_data

    payload = {
        'videoId': video_id,
        'contentCheckOk': True,
        'racyCheckOk': True,
        'context': {'client': context},
    }
    if client.params:
        payload['params'] = client.params
        payload['cpn'] = ''.join(random.choice(_CPN_ALPHABET) for _ in range(16))

    return http.post_json(PLAYER_URL, payload, headers)


def _is_playable(response, video_id):
    # For a video it may not show in this app, YouTube answers with another one.
    return (response.get('playabilityStatus', {}).get('status') == 'OK'
            and response.get('videoDetails', {}).get('videoId') == video_id)
