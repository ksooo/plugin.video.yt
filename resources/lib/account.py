# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The signed-in YouTube account: signing in and out, and the access tokens.

Signing in grants access to the OAuth client of YouTube's app for Meta Quest,
whose identity the add-on uses for everything concerning the account. The
tokens are kept in the profile directory, not in the settings.
"""

import os
import time

import xbmc
import xbmcgui

from . import addon
from . import feeds
from . import http
from . import innertube
from . import oauth

TOKENS_FILE = 'tokens.json'
#: Data of the account kept besides the tokens, see subscriptions.py and
#: likes.py. It goes when the account does.
SUBSCRIPTIONS_FILE = 'subscriptions.json'
LIKES_FILE = 'likes.json'

#: Account key used in the tokens file and by innertube.Client.account.
VR = 'vr'
#: The key of the user's own OAuth client, which older versions of the add-on
#: signed in to as well.
_USER = 'user'

#: An access token this close to its expiry is renewed before use.
EXPIRY_MARGIN_SECONDS = 60

#: How often the sign-in dialogue checks whether it was cancelled.
CANCEL_CHECK_SECONDS = 0.5


def sign_in():
    """Grant YouTube's app for Meta Quest access and keep the tokens if that succeeds."""
    try:
        tokens = _authorize(oauth.YOUTUBE_VR, addon.localize(30016), addon.localize(30113))
    except (oauth.OAuthError, http.RequestError) as error:
        addon.log_error('sign-in failed: {}'.format(error))
        addon.notify(addon.localize(30122))
        return

    if tokens is None:
        addon.log('sign-in cancelled')
        return

    _save({VR: tokens})
    addon.set_bool_setting(addon.SETTING_SIGNED_IN, True)
    update_name()
    addon.notify(addon.localize(30120))


def sign_out():
    """Revoke and forget all tokens."""
    _revoke(_load())
    _forget()
    addon.notify(addon.localize(30121))


def update_name():
    """Fetch the account's name for the settings to show."""
    token = access_token(VR)
    if token is None:
        return
    try:
        name = innertube.get_account_name(addon.language(), addon.region(), token)
    except http.RequestError as error:
        addon.log_error('fetching the account name failed: {}'.format(error))
        return
    addon.set_string_setting(addon.SETTING_ACCOUNT_NAME, name)


def is_signed_in():
    return VR in _load()


def access_token(key):
    """Return a valid access token of the account, or None when not signed in.

    An expired token is renewed. If Google refuses that - the user revoked the
    access - the add-on signs out.
    """
    all_tokens = _load()
    tokens = all_tokens.get(key)
    if tokens is None:
        return None
    if tokens['expires_at'] - EXPIRY_MARGIN_SECONDS > time.time():
        return tokens['access_token']

    try:
        all_tokens[key] = oauth.refresh(oauth.YOUTUBE_VR, tokens['refresh_token'])
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


def sync_token():
    """Return the token to sync the watch history with, None if not to sync."""
    if not addon.get_bool_setting(addon.SETTING_SYNC_PLAYBACK):
        return None
    return access_token(VR)


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
    tokens = addon.load_json(addon.profile_path(TOKENS_FILE), {})
    if tokens.pop(_USER, None) is not None:
        _save(tokens)
    return tokens


def _save(tokens):
    addon.save_json(addon.profile_path(TOKENS_FILE), tokens)


def _forget():
    # The feeds kept in Kodi's temp directory belong to the account too.
    paths = [addon.profile_path(TOKENS_FILE), addon.profile_path(SUBSCRIPTIONS_FILE),
             addon.profile_path(LIKES_FILE), addon.temp_path(feeds.SHELVES_FILE),
             addon.temp_path(feeds.PROGRESS_FILE), addon.temp_path(feeds.REMOVED_FILE)]
    for path in paths:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    addon.set_bool_setting(addon.SETTING_SIGNED_IN, False)
    addon.set_string_setting(addon.SETTING_ACCOUNT_NAME, '')
