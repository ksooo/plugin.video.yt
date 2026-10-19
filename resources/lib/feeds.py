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

How far the account watched the videos of its history is kept for
PROGRESS_MAX_AGE_SECONDS as well, since every video listing needs it.

YouTube still delivers a video just removed from the history for a while, so
such a video is left out of the history and its progress for
REMOVED_MAX_AGE_SECONDS, unless it is watched again.

The video Kodi plays, or played last, is noted for the service, which runs
apart from the playback.
"""

import time

from . import addon
from . import innertube

SHELVES_FILE = 'recommendations.json'
SHELVES_MAX_AGE_SECONDS = 15 * 60

PROGRESS_FILE = 'watch-progress.json'
PROGRESS_MAX_AGE_SECONDS = 5 * 60

REMOVED_FILE = 'removed-from-history.json'
REMOVED_MAX_AGE_SECONDS = 5 * 60

PLAYBACK_FILE = 'playback.json'


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
    removed = _recently_removed()
    video_ids = []
    for shelf in innertube.get_shelves(innertube.HISTORY, addon.language(), addon.region(),
                                       access_token):
        video_ids.extend(video_id for video_id in shelf.video_ids
                         if video_id not in video_ids and video_id not in removed)
    return video_ids


def watch_progress(access_token):
    """Return how many percent of each video in the watch history the account watched."""
    path = addon.temp_path(PROGRESS_FILE)
    cache = addon.load_json(path, None)
    if cache is not None and time.time() - cache['saved_at'] < PROGRESS_MAX_AGE_SECONDS:
        return cache['progress']

    progress = innertube.get_watch_progress(addon.language(), addon.region(), access_token)
    for video_id in _recently_removed():
        progress.pop(video_id, None)
    addon.save_json(path, {'saved_at': time.time(), 'progress': progress})
    return progress


def watched(video_id, percent):
    """Note how far the video was just watched in Kodi, before YouTube's history shows it.

    YouTube keeps the furthest position reported, and so does this.
    """
    removals = _recently_removed()
    if removals.pop(video_id, None) is not None:
        addon.save_json(addon.temp_path(REMOVED_FILE), removals)

    path = addon.temp_path(PROGRESS_FILE)
    cache = addon.load_json(path, None)
    if cache is not None:
        progress = cache['progress']
        progress[video_id] = max(percent, progress.get(video_id, 0))
        addon.save_json(path, cache)


def removed(video_id):
    """Note that the video was just removed from the watch history."""
    removals = _recently_removed()
    removals[video_id] = time.time()
    addon.save_json(addon.temp_path(REMOVED_FILE), removals)

    path = addon.temp_path(PROGRESS_FILE)
    cache = addon.load_json(path, None)
    if cache is not None and cache['progress'].pop(video_id, None) is not None:
        addon.save_json(path, cache)


def playback_started(video_id):
    """Note that Kodi plays the video, until playback_ended()."""
    addon.save_json(addon.temp_path(PLAYBACK_FILE), {'video_id': video_id, 'ended_at': None})


def playback_ended(video_id):
    """Note that Kodi stopped playing the video."""
    addon.save_json(addon.temp_path(PLAYBACK_FILE),
                    {'video_id': video_id, 'ended_at': time.time()})


def played_lately(video_id, seconds):
    """Return whether Kodi plays the video, or stopped playing it within the seconds."""
    playback = addon.load_json(addon.temp_path(PLAYBACK_FILE), {})
    if playback.get('video_id') != video_id:
        return False
    return playback['ended_at'] is None or time.time() - playback['ended_at'] < seconds


def _recently_removed():
    """Return when the videos were removed from the history lately, by id."""
    now = time.time()
    return {video_id: removed_at
            for video_id, removed_at in addon.load_json(addon.temp_path(REMOVED_FILE), {}).items()
            if now - removed_at < REMOVED_MAX_AGE_SECONDS}
