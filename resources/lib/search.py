# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Searching: the recent searches, and the results of the last minutes.

The recent searches survive restarts in the profile directory, the results do
not: they are kept for RESULTS_MAX_AGE_SECONDS in Kodi's temp directory, since
a search costs 101 quota units and going back to the results would otherwise
search anew.
"""

from . import addon
from . import dataapi

HISTORY_FILE = 'searches.json'
HISTORY_SIZE = 20

RESULTS_FILE = 'search-results.json'
RESULTS_MAX_AGE_SECONDS = 15 * 60


def recent():
    """Return the recent searches, the newest first."""
    return addon.load_json(addon.profile_path(HISTORY_FILE), [])


def remember(query):
    """Put the query on top of the recent searches."""
    queries = [query] + [known for known in recent() if known != query]
    addon.save_json(addon.profile_path(HISTORY_FILE), queries[:HISTORY_SIZE])


def forget(query):
    """Remove the query from the recent searches."""
    addon.save_json(addon.profile_path(HISTORY_FILE),
                    [known for known in recent() if known != query])


def results(query, region, language, count, auth):
    """Return the videos found for the query, from the cache if searched for lately."""
    videos = addon.cached(RESULTS_FILE, '\n'.join((query, region, language, str(count))),
                          RESULTS_MAX_AGE_SECONDS,
                          lambda: dataapi.search(query, region, language, count, auth=auth))
    return [dataapi.Video(*video) for video in videos]
