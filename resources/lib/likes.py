# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The videos the account liked, cached for the context menus.

Every video listing needs them, to offer liking a video or taking the like
back. Listing the likes, liking and taking a like back bring the cache up to
date; otherwise it is fetched again after MAX_AGE_SECONDS.
"""

import time

from . import account
from . import addon
from . import innertube

MAX_AGE_SECONDS = 3600


def list_ids(access_token):
    """Return the ids of the liked videos, the latest like first, freshly from YouTube."""
    video_ids = innertube.get_liked_video_ids(addon.language(), addon.region(), access_token)
    _save(video_ids)
    return video_ids


def liked_ids(access_token):
    """Return the ids of the liked videos, from the cache while it is recent."""
    cache = _load()
    if cache is not None and time.time() - cache['saved_at'] < MAX_AGE_SECONDS:
        return cache['videos']
    return list_ids(access_token)


def like(video_id, access_token):
    video_ids = liked_ids(access_token)
    innertube.like(video_id, addon.language(), addon.region(), access_token)
    _save([video_id] + [liked for liked in video_ids if liked != video_id])


def remove_like(video_id, access_token):
    video_ids = liked_ids(access_token)
    innertube.remove_like(video_id, addon.language(), addon.region(), access_token)
    _save([liked for liked in video_ids if liked != video_id])


def _load():
    return addon.load_json(addon.profile_path(account.LIKES_FILE), None)


def _save(video_ids):
    addon.save_json(addon.profile_path(account.LIKES_FILE),
                    {'saved_at': time.time(), 'videos': video_ids})
