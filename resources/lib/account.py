# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The signed-in YouTube account: signing in and out, and the access tokens.

Signing in grants access twice, to two OAuth clients: the user's own one for
the YouTube Data API, and the one of YouTube's app for Meta Quest, whose
player requests may fetch age-restricted videos. The tokens are kept in the
profile directory, not in the settings.
"""

import json
import os
import time

import xbmc
import xbmcgui

from . import addon
from . import http
from . import oauth

TOKENS_FILE = 'tokens.json'

#: Account keys used in the tokens file and by innertube.Client.account.
USER = 'user'
VR = 'vr'

#: An access token this close to its expiry is renewed before use.
EXPIRY_MARGIN_SECONDS = 60

#: How often the sign-in dialogue checks whether it was cancelled.
CANCEL_CHECK_SECONDS = 0.5


def _own_client():
    return oauth.Client(addon.get_string_setting(addon.SETTING_CLIENT_ID),
                        addon.get_string_setting(addon.SETTING_CLIENT_SECRET))


#: The sign-in steps: account key, OAuth client and what the access is for.
_STEPS = (
    (USER, _own_client, 30112),
    (VR, lambda: oauth.YOUTUBE_VR, 30113),
)


def sign_in():
    """Run through the sign-in steps and keep the tokens if all of them succeed."""
    tokens = {}
    for number, (key, client, purpose_id) in enumerate(_STEPS, start=1):
        try:
            result = _authorize(client(), addon.localize(30110).format(number, len(_STEPS)),
                                addon.localize(purpose_id))
        except (oauth.OAuthError, http.RequestError) as error:
            addon.log_error('sign-in failed: {}'.format(error))
            _revoke(tokens)
            addon.notify(addon.localize(30122))
            return

        if result is None:
            addon.log('sign-in cancelled')
            _revoke(tokens)
            return
        tokens[key] = result

    _save(tokens)
    addon.set_bool_setting(addon.SETTING_SIGNED_IN, True)
    addon.notify(addon.localize(30120))


def sign_out():
    """Revoke and forget all tokens."""
    _revoke(_load())
    _forget()
    addon.notify(addon.localize(30121))


def access_token(key):
    """Return a valid access token of the account, or None when not signed in.

    An expired token is renewed. If Google refuses that - the user revoked the
    access, or the OAuth client in the settings changed - the add-on signs out.
    """
    all_tokens = _load()
    tokens = all_tokens.get(key)
    if tokens is None:
        return None
    if tokens['expires_at'] - EXPIRY_MARGIN_SECONDS > time.time():
        return tokens['access_token']

    client = _own_client() if key == USER else oauth.YOUTUBE_VR
    try:
        all_tokens[key] = oauth.refresh(client, tokens['refresh_token'])
    except oauth.OAuthError as error:
        addon.log_error('renewing the {} token failed: {}'.format(key, error))
        _forget()
        addon.notify(addon.localize(30123))
        return None
    except http.RequestError as error:
        addon.log_error(str(error))
        return None

    _save(all_tokens)
    return all_tokens[key]['access_token']


def _authorize(client, heading, purpose):
    """Show the code to enter until the user did so or cancelled."""
    dialog = xbmcgui.DialogProgress()
    monitor = xbmc.Monitor()

    def show_code(url, code):
        dialog.update(0, '{}[CR][CR]{}'.format(addon.localize(30111).format(url, code),
                                               purpose))

    def wait(seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if dialog.iscanceled() or monitor.waitForAbort(CANCEL_CHECK_SECONDS):
                return False
        return True

    # Open at once, fetching the code from Google takes a moment.
    dialog.create(heading, addon.localize(30114))
    try:
        return oauth.authorize(client, show_code, wait)
    finally:
        dialog.close()


def _revoke(all_tokens):
    for tokens in all_tokens.values():
        oauth.revoke(tokens['refresh_token'])


def _load():
    try:
        with open(addon.profile_path(TOKENS_FILE), encoding='utf-8') as tokens_file:
            return json.load(tokens_file)
    except (OSError, ValueError):
        return {}


def _save(tokens):
    with open(addon.profile_path(TOKENS_FILE), 'w', encoding='utf-8') as tokens_file:
        json.dump(tokens, tokens_file)


def _forget():
    try:
        os.remove(addon.profile_path(TOKENS_FILE))
    except FileNotFoundError:
        pass
    addon.set_bool_setting(addon.SETTING_SIGNED_IN, False)
