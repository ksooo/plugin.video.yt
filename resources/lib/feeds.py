# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The signed-in account's recommendations and watch history.

The Data API has neither, so InnerTube delivers the video ids; the details
come from the Data API as everywhere else.

The recommendations come in shelves that change with every request and have
no id of their own. The shelves last listed are therefore kept for
SHELVES_MAX_AGE_SECONDS in Kodi's temp directory, so that opening one shows
what the list of shelves promised. A shelf is found by its title.
"""

import time

from . import addon
from . import innertube

SHELVES_FILE = 'recommendations.json'
SHELVES_MAX_AGE_SECONDS = 15 * 60


def recommendation_shelves(access_token):
    """Return the shelves of recommendations, freshly from YouTube."""
    shelves = innertube.get_shelves(innertube.RECOMMENDATIONS, addon.language(), addon.region(),
                                    access_token)
    addon.save_json(addon.temp_path(SHELVES_FILE), {'saved_at': time.time(), 'shelves': shelves})
    return shelves


def recommendation_shelf(title, access_token):
    """Return the shelf of recommendations with the title last listed, None if gone."""
    cache = addon.load_json(addon.temp_path(SHELVES_FILE), None)
    if cache is not None and time.time() - cache['saved_at'] < SHELVES_MAX_AGE_SECONDS:
        shelves = [innertube.Shelf(*shelf) for shelf in cache['shelves']]
    else:
        shelves = recommendation_shelves(access_token)
    return next((shelf for shelf in shelves if shelf.title == title), None)


def history(access_token):
    """Return the ids of the videos watched last, the latest first."""
    video_ids = []
    for shelf in innertube.get_shelves(innertube.HISTORY, addon.language(), addon.region(),
                                       access_token):
        video_ids.extend(video_id for video_id in shelf.video_ids if video_id not in video_ids)
    return video_ids
