# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Google's OAuth 2.0 flow for TVs and limited-input devices.

https://developers.google.com/identity/protocols/oauth2/limited-input-device
"""

import collections
import time

from . import http

DEVICE_CODE_URL = 'https://oauth2.googleapis.com/device/code'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
DEVICE_GRANT_TYPE = 'urn:ietf:params:oauth:grant-type:device_code'
SCOPE = 'https://www.googleapis.com/auth/youtube'

#: Google wants a poll interval raised by 5 seconds on every "slow_down".
SLOW_DOWN_SECONDS = 5

Client = collections.namedtuple('Client', 'client_id client_secret')

#: The client of YouTube's app for Meta Quest. Its tokens are what YouTube
#: accepts from that app, see innertube.ANDROID_VR.
YOUTUBE_VR = Client('652469312169-4lvs9bnhr9lpns9v451j5oivd81vjvu1.apps.googleusercontent.com',
                    '3fTWrBJI5Uojm1TK7_iJCW5Z')


class OAuthError(Exception):
    """Google refused. The message is Google's error code, e.g. 'access_denied'."""


def authorize(client, show_code, wait):
    """Let the user grant access on another device and return the tokens.

    show_code(verification_url, user_code) is called once with what the user
    has to enter. wait(seconds) waits between two polls and returns False when
    the user gives up, in which case the result is None.
    """
    code = _checked(http.post_form(DEVICE_CODE_URL, {
        'client_id': client.client_id,
        'scope': SCOPE,
    }))
    show_code(code['verification_url'], code['user_code'])

    interval = int(code.get('interval', 5))
    while wait(interval):
        response = http.post_form(TOKEN_URL, {
            'client_id': client.client_id,
            'client_secret': client.client_secret,
            'device_code': code['device_code'],
            'grant_type': DEVICE_GRANT_TYPE,
        })
        error = response.get('error')
        if error == 'authorization_pending':
            continue
        if error == 'slow_down':
            interval += SLOW_DOWN_SECONDS
            continue
        return _tokens(_checked(response))

    return None


def refresh(client, refresh_token):
    """Return new tokens for the refresh token. They carry the refresh token too."""
    tokens = _tokens(_checked(http.post_form(TOKEN_URL, {
        'client_id': client.client_id,
        'client_secret': client.client_secret,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    })))
    tokens.setdefault('refresh_token', refresh_token)
    return tokens


def revoke(token):
    """Revoke the token and everything granted with it. Failures are ignored."""
    try:
        http.post_form(REVOKE_URL, {'token': token})
    except http.RequestError:
        pass


def _checked(response):
    if 'error' in response:
        raise OAuthError(response['error'])
    return response


def _tokens(response):
    tokens = {
        'access_token': response['access_token'],
        'expires_at': time.time() + int(response['expires_in']),
    }
    if 'refresh_token' in response:
        tokens['refresh_token'] = response['refresh_token']
    return tokens
