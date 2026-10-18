# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The newest uploads of channels, from YouTube's RSS feeds, which cost no quota.

A feed holds the 15 newest videos of a playlist. The channel's UULF playlist
is its Videos tab, as in the channel listings: no shorts, no live recordings.
"""

from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ElementTree

from . import addon
from . import http
from . import innertube

FEED_URL = 'https://www.youtube.com/feeds/videos.xml?playlist_id={}'

#: How many feeds are fetched at once.
PARALLEL_FEEDS = 8

_NAMESPACES = {'atom': 'http://www.w3.org/2005/Atom',
               'yt': 'http://www.youtube.com/xml/schemas/2015'}


def uploads(channel_ids):
    """Return the ids of the newest videos of the channels, the newest first.

    A channel whose feed fails is left out, after logging why.
    """
    with ThreadPoolExecutor(PARALLEL_FEEDS) as pool:
        entries = [entry for feed in pool.map(_feed, channel_ids) for entry in feed]
    return [video_id for _, video_id in sorted(entries, reverse=True)]


def _feed(channel_id):
    """Return (published, video id) of the videos in the channel's feed."""
    url = FEED_URL.format('UULF' + channel_id[2:])
    try:
        body = http.get(url, innertube.WEB.stream_headers)
        # A channel without a single video has no such playlist.
        if body is None:
            return []
        root = ElementTree.fromstring(body)
    except (http.RequestError, ElementTree.ParseError) as error:
        addon.log_error('feed of {}: {}'.format(channel_id, error))
        return []
    return [(entry.findtext('atom:published', '', _NAMESPACES),
             entry.findtext('yt:videoId', '', _NAMESPACES))
            for entry in root.findall('atom:entry', _NAMESPACES)]
