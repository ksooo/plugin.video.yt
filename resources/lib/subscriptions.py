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
a video's channel. Listing the subscriptions, subscribing and unsubscribing
bring the cache up to date; otherwise it is fetched again after
MAX_AGE_SECONDS.
"""

from concurrent.futures import ThreadPoolExecutor
import time

from . import account
from . import addon
from . import dataapi
from . import innertube

MAX_AGE_SECONDS = 3600

#: How many channels are asked for their newest videos at once.
PARALLEL_CHANNELS = 16


def list_channels(access_token):
    """Return the subscribed channels, freshly from YouTube."""
    channels = innertube.get_subscribed_channels(addon.language(), addon.region(), access_token)
    _save([channel.channel_id for channel in channels])
    return channels


def channel_ids(access_token):
    """Return the ids of the subscribed channels, from the cache while it is recent."""
    cache = _load()
    # Older versions of the add-on cached subscription ids instead.
    if (cache is not None and 'channel_ids' in cache
            and time.time() - cache['saved_at'] < MAX_AGE_SECONDS):
        return cache['channel_ids']
    return [channel.channel_id for channel in list_channels(access_token)]


def latest_video_ids(count, access_token, auth):
    """Return the ids of the newest videos of all subscribed channels, the newest first.

    1 unit per channel.
    """
    with ThreadPoolExecutor(PARALLEL_CHANNELS) as pool:
        uploads = [upload for channel in pool.map(
            lambda channel_id: dataapi.channel_uploads(channel_id, dataapi.PAGE_SIZE, auth=auth),
            channel_ids(access_token)) for upload in channel]
    return [video_id for _, video_id in sorted(uploads, reverse=True)[:count]]


def subscribe(channel_id, access_token):
    ids = channel_ids(access_token)
    innertube.subscribe(channel_id, addon.language(), addon.region(), access_token)
    _save([subscribed for subscribed in ids if subscribed != channel_id] + [channel_id])


def unsubscribe(channel_id, access_token):
    ids = channel_ids(access_token)
    innertube.unsubscribe(channel_id, addon.language(), addon.region(), access_token)
    _save([subscribed for subscribed in ids if subscribed != channel_id])


def _load():
    return addon.load_json(addon.profile_path(account.SUBSCRIPTIONS_FILE), None)


def _save(ids):
    addon.save_json(addon.profile_path(account.SUBSCRIPTIONS_FILE),
                    {'saved_at': time.time(), 'channel_ids': ids})
