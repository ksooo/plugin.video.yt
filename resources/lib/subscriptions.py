# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The channels the account subscribed to, cached for the context menus.

Every video listing needs them, to offer subscribing to or unsubscribing from
a video's channel. The cache maps channel ids to subscription ids, which
unsubscribing takes. Listing the subscriptions, subscribing and unsubscribing
bring it up to date; otherwise it is fetched again after MAX_AGE_SECONDS.
"""

import json
import time

from . import account
from . import addon
from . import dataapi

MAX_AGE_SECONDS = 3600


def list_channels(token):
    """Return the subscribed channels, freshly from YouTube."""
    channels = dataapi.subscriptions(token=token)
    _save({channel.channel_id: channel.subscription_id for channel in channels})
    return channels


def subscription_ids(token):
    """Return the subscription ids by channel id, from the cache while it is recent."""
    cache = _load()
    if cache is not None and time.time() - cache['saved_at'] < MAX_AGE_SECONDS:
        return cache['channels']
    return _fresh_ids(token)


def subscribe(channel_id, token):
    ids = subscription_ids(token)
    ids[channel_id] = dataapi.subscribe(channel_id, token=token)
    _save(ids)


def unsubscribe(channel_id, token):
    ids = subscription_ids(token)
    if channel_id not in ids:
        # Subscribed on another device since the cache was saved.
        ids = _fresh_ids(token)
    if channel_id in ids:
        dataapi.unsubscribe(ids.pop(channel_id), token=token)
        _save(ids)


def _fresh_ids(token):
    return {channel.channel_id: channel.subscription_id for channel in list_channels(token)}


def _load():
    try:
        with open(addon.profile_path(account.SUBSCRIPTIONS_FILE),
                  encoding='utf-8') as cache_file:
            return json.load(cache_file)
    except (OSError, ValueError):
        return None


def _save(ids):
    with open(addon.profile_path(account.SUBSCRIPTIONS_FILE), 'w',
              encoding='utf-8') as cache_file:
        json.dump({'saved_at': time.time(), 'channels': ids}, cache_file)
