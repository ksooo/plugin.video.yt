# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Reporting playback in Kodi to the account's watch history, as YouTube's apps do.

The player response's playbackTracking holds the URLs to report to: one for
the start of a playback, one for the time watched since the last report.
YouTube keeps the furthest position ever reported, a smaller one changes
nothing.
"""

from urllib.parse import urlencode

import xbmc

from . import account
from . import addon
from . import http
from . import innertube

#: How often the time watched is reported, as YouTube's apps do.
REPORT_INTERVAL_SECONDS = 10

#: How long Kodi may take to start playing after the URL is resolved.
START_TIMEOUT_SECONDS = 30


class _Report:
    """The reports of one playback."""

    def __init__(self, tracking):
        self._tracking = tracking
        self._params = {'cpn': innertube.new_cpn(), 'ver': '2', 'fs': '0', 'volume': '100',
                        'muted': '0'}

    def started(self):
        self._send('videostatsPlaybackUrl')

    def watched(self, start, end, state):
        """Report the time from start to end, in seconds, and the player's state then."""
        self._send('videostatsWatchtimeUrl', st='{:.3f}'.format(min(start, end)),
                   et='{:.3f}'.format(end), cmt='{:.3f}'.format(end), state=state)

    def _send(self, url_key, **params):
        # Long videos outlast an access token.
        token = account.access_token(account.VR)
        if token is None:
            return
        url = '{}&{}'.format(self._tracking[url_key]['baseUrl'],
                             urlencode(dict(self._params, **params)))
        try:
            http.request_json('GET', url, dict(innertube.ANDROID_VR.stream_headers,
                                               Authorization='Bearer ' + token))
        except http.RequestError as error:
            addon.log_error('reporting playback failed: {}'.format(error))


def follow(url, tracking):
    """Report the playback of url to the watch history for as long as Kodi plays it.

    Returns the position, in seconds, playback stopped at; None if it never
    started or Kodi is shutting down.
    """
    monitor = xbmc.Monitor()
    player = xbmc.Player()
    waited = 0
    position = _position(player, url)
    while position is None:
        if waited >= START_TIMEOUT_SECONDS or monitor.waitForAbort(1):
            return None
        waited += 1
        position = _position(player, url)

    report = _Report(tracking)
    report.started()
    reported = position
    seconds = 0
    while not monitor.waitForAbort(1):
        current = _position(player, url)
        if current is None:
            report.watched(reported, position, 'stopped')
            return position
        position = current
        seconds += 1
        if seconds % REPORT_INTERVAL_SECONDS == 0:
            report.watched(reported, position,
                           'paused' if xbmc.getCondVisibility('Player.Paused') else 'playing')
            reported = position
    return None


def _position(player, url):
    """Return the position Kodi plays url at, None if it plays something else or nothing."""
    try:
        if player.getPlayingFile() == url:
            return player.getTime()
    except RuntimeError:
        # Kodi is not playing anything.
        pass
    return None
