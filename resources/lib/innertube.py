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

    def __init__(self, client_id, context, user_agent, origin, params=None, account=None):
        self.client_id = client_id
        self.context = context
        self.params = params
        #: Key of the account whose access token the app accepts, see account.py.
        self.account = account
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

#: The app for Meta Quest. Offers the original audio track only, but signed in
#: it gets age-restricted videos too.
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
    'https://www.youtube.com',
    account='vr')

#: Player clients by preference.
PLAYER_CLIENTS = (ANDROID, ANDROID_VR)

#: A player response and the client it was given to.
Player = collections.namedtuple('Player', 'response client')

_CPN_ALPHABET = string.ascii_letters + string.digits + '-_'


#: Refusals that a signed-in client may get past, e.g. for age-restricted videos.
_SIGN_IN_STATUSES = frozenset(('LOGIN_REQUIRED', 'AGE_CHECK_REQUIRED',
                               'AGE_VERIFICATION_REQUIRED', 'CONTENT_CHECK_REQUIRED'))


class PlayabilityError(Exception):
    """YouTube refuses to play the video. The message is YouTube's reason, if it gave one.

    sign_in_would_help tells whether YouTube asked for a sign-in while a client
    that accepts one was asked without.
    """

    def __init__(self, reason, sign_in_would_help=False):
        super().__init__(reason)
        self.sign_in_would_help = sign_in_would_help


def get_player(video_id, language, region, access_token):
    """Return the player response of the first client YouTube serves the video to.

    language and region are ISO codes such as 'de' and 'DE'; YouTube words its
    reasons for refusing a video in that language. Either may be empty.
    access_token(account) returns the token of a signed-in account, or None.
    """
    reasons = []
    asked_for_sign_in = False
    signed_out_client = False
    for client in PLAYER_CLIENTS:
        token = access_token(client.account) if client.account else None
        signed_out_client = signed_out_client or (client.account is not None and token is None)
        response = _request_player(client, video_id, language, region, token)
        if not _is_playable(response, video_id):
            # Refusals such as YouTube's bot check carry a visitor id that
            # passes it.
            visitor_data = response.get('responseContext', {}).get('visitorData')
            if visitor_data:
                response = _request_player(client, video_id, language, region, token,
                                           visitor_data)

        if _is_playable(response, video_id):
            return Player(response, client)

        status = response.get('playabilityStatus', {})
        reasons.append(status.get('reason', ''))
        asked_for_sign_in = asked_for_sign_in or status.get('status') in _SIGN_IN_STATUSES

    raise PlayabilityError(next((reason for reason in reasons if reason), ''),
                           asked_for_sign_in and signed_out_client)


def _request_player(client, video_id, language, region, token, visitor_data=None):
    context = dict(client.context)
    headers = client.api_headers
    if token:
        headers['Authorization'] = 'Bearer ' + token
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
