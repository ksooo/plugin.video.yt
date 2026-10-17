# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Passing on to the account's watch history what Kodi changes of the add-on's videos.

Kodi announces changes of a file's play count and resume point as
Files.OnPlayCountChanged and Files.OnResumePointChanged, e.g. from "Mark as
watched" or "Reset resume position" in the context menu. Kodi versions that do
not announce them leave the service waiting.

YouTube keeps the furthest position reported, so a smaller one only gets
through after removing the video from the history.
"""

import json
import time
from urllib.parse import parse_qsl
from urllib.parse import urlsplit

import xbmc

from . import account
from . import addon
from . import feeds
from . import http
from . import innertube
from . import listing
from . import watchtime

PLAY_COUNT_CHANGED = 'Files.OnPlayCountChanged'
RESUME_POINT_CHANGED = 'Files.OnResumePointChanged'

#: Marking a video watched or unwatched, and playing it to the end, reset its
#: resume point just before changing its play count. A reset without a play
#: count following within this time stands on its own.
PLAY_COUNT_WAIT_SECONDS = 2


class Service(xbmc.Monitor):
    """Waits for Kodi's announcements until Kodi shuts down."""

    def __init__(self):
        super().__init__()
        #: Video ids whose resume point was reset, with the time it was.
        self._resets = {}

    def run(self):
        while not self.waitForAbort(1):
            self.handle_resets(time.monotonic())

    def onNotification(self, sender, method, data):
        if method not in (PLAY_COUNT_CHANGED, RESUME_POINT_CHANGED):
            return
        data = json.loads(data)
        video_id = _video_id(data.get('file', ''))
        if video_id is None:
            return

        if method == PLAY_COUNT_CHANGED:
            self._resets.pop(video_id, None)
            if data['playcount'] > 0:
                _sync(_report, video_id, None)
            else:
                _sync(_remove, video_id)
        elif data['resume']['position'] > 0:
            _sync(_replace, video_id, data['resume']['position'])
        else:
            self._resets[video_id] = time.monotonic()

    def handle_resets(self, now):
        """Remove the videos whose resume point was reset on its own from the history."""
        for video_id, reset_at in list(self._resets.items()):
            if now - reset_at >= PLAY_COUNT_WAIT_SECONDS:
                del self._resets[video_id]
                _sync(_remove, video_id)


def run():
    Service().run()


def _video_id(file):
    """Return the id of the video the add-on plays from the plugin URL, None for any other file."""
    if not file.startswith(listing.url('play')):
        return None
    return dict(parse_qsl(urlsplit(file).query)).get('v')


def _sync(change, video_id, *args):
    """Apply a change to the watch history, if syncing, and show it."""
    token = account.sync_token()
    if token is None:
        return
    try:
        changed = change(video_id, token, *args)
    except http.RequestError as error:
        addon.log_error(str(error))
        return
    # Kodi lists a folder anew right after changing a video in it, before the
    # history has the change.
    if changed and xbmc.getInfoLabel('Container.FolderPath').startswith(listing.BASE_URL):
        xbmc.executebuiltin('Container.Refresh')


def _remove(video_id, token):
    """Remove the video from the history. Returns whether it was there."""
    if not innertube.remove_from_history(video_id, addon.language(), addon.region(), token):
        return False
    feeds.removed(video_id)
    return True


def _replace(video_id, token, position):
    """Replace the position the history has for the video, even by an earlier one."""
    removed = _remove(video_id, token)
    return _report(video_id, token, position) or removed


def _report(video_id, token, position):
    """Report the video watched up to position, in seconds; None for to the end.

    Returns whether YouTube got the report.
    """
    response = innertube.get_signed_in_player(video_id, addon.language(), addon.region(), token)
    tracking = response.get('playbackTracking') if response else None
    if not tracking:
        addon.log('{} cannot be reported to the watch history'.format(video_id))
        return False

    length = int(response['videoDetails'].get('lengthSeconds', 0))
    if position is None:
        position = length
    watchtime.report(tracking, position)
    if length:
        feeds.watched(video_id, min(100, round(position * 100 / length)))
    return True
