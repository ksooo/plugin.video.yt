# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The categories of trending videos: those of Kodi's region YouTube has a chart for.

Which categories have a chart only shows by asking for it, a unit each. The
categories found are therefore kept for MAX_AGE_SECONDS in Kodi's temp
directory, by region and language, together with the thumbnail of their most
popular video, which asking brings along. The same goes for the chart of all
categories.
"""

import collections

from . import addon
from . import dataapi

CATEGORIES_FILE = 'trending-categories.json'
MAX_AGE_SECONDS = 24 * 60 * 60

#: How YouTube refuses a category it has no chart for.
_NO_CHART = ('notFound', 'videoChartNotFound')

#: A category with a chart, and the thumbnail of its most popular video. The
#: category id of all categories is empty.
TrendingCategory = collections.namedtuple('TrendingCategory', 'category_id title thumbnail')


def region():
    """Return Kodi's region, or YouTube's default if Kodi has none."""
    return addon.region() or 'US'


def categories(auth):
    """Return all categories as one, then those with a chart in YouTube's order.

    The first one, standing for all categories, has no title.
    """
    found = addon.cached(CATEGORIES_FILE, '{}/{}'.format(region(), addon.language()),
                         MAX_AGE_SECONDS, lambda: _categories_with_chart(auth))
    return [TrendingCategory(*category) for category in found]


def _categories_with_chart(auth):
    found = []
    for category in [dataapi.Category('', '')] + dataapi.video_categories(
            region(), addon.language(), auth=auth):
        try:
            videos = dataapi.most_popular(region(), category.category_id or None, 1, auth=auth)
        except dataapi.DataApiError as error:
            if str(error) not in _NO_CHART:
                raise
            continue
        if videos:
            found.append(TrendingCategory(category.category_id, category.title,
                                          videos[0].thumbnail))
    return found
