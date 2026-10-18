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

import time

from . import account
from . import addon
from . import dataapi
from . import rss

MAX_AGE_SECONDS = 3600


def list_channels(auth):
    """Return the subscribed channels, freshly from YouTube."""
    channels = dataapi.subscriptions(auth=auth)
    _save({channel.channel_id: channel.subscription_id for channel in channels})
    return channels


def subscription_ids(auth):
    """Return the subscription ids by channel id, from the cache while it is recent."""
    cache = _load()
    if cache is not None and time.time() - cache['saved_at'] < MAX_AGE_SECONDS:
        return cache['channels']
    return _fresh_ids(auth)


def latest_video_ids(count, auth):
    """Return the ids of the newest videos of all subscribed channels, the newest first."""
    return rss.uploads(list(subscription_ids(auth)))[:count]


def subscribe(channel_id, auth):
    ids = subscription_ids(auth)
    ids[channel_id] = dataapi.subscribe(channel_id, auth=auth)
    _save(ids)


def unsubscribe(channel_id, auth):
    ids = subscription_ids(auth)
    if channel_id not in ids:
        # Subscribed on another device since the cache was saved.
        ids = _fresh_ids(auth)
    if channel_id in ids:
        dataapi.unsubscribe(ids.pop(channel_id), auth=auth)
        _save(ids)


def _fresh_ids(auth):
    return {channel.channel_id: channel.subscription_id for channel in list_channels(auth)}


def _load():
    return addon.load_json(addon.profile_path(account.SUBSCRIPTIONS_FILE), None)


def _save(ids):
    addon.save_json(addon.profile_path(account.SUBSCRIPTIONS_FILE),
                    {'saved_at': time.time(), 'channels': ids})
