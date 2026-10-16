# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Routing of plugin calls.

Every listing and every action has a path of its own below the add-on root,
e.g. plugin://plugin.video.yt/play/?v=<id>. Kodi stores resume points and play
counts under these URLs, so the URL of a video must never change.
"""

from urllib.parse import parse_qsl
from urllib.parse import urlsplit

import xbmcplugin

from . import account
from . import addon
from . import dataapi
from . import http
from . import listing
from . import playback

#: The most videos listed for a channel.
CHANNEL_VIDEO_COUNT = 100


class Router:
    """Dispatches a single plugin invocation."""

    def __init__(self, argv):
        self._route = urlsplit(argv[0]).path.strip('/')
        self._handle = int(argv[1])
        self._params = dict(parse_qsl(argv[2].lstrip('?')))

    def dispatch(self):
        """Execute the action requested by the caller."""
        handler = _ROUTES.get(self._route)
        if handler is None:
            addon.log_error('unknown route: {}'.format(self._route))
            xbmcplugin.endOfDirectory(self._handle, succeeded=False)
            return

        handler(self)

    def _list_root(self):
        """Show the top level of the add-on."""
        items = []
        if account.is_signed_in():
            items.append(listing.folder_item(addon.localize(30200), 'subscriptions'))
        listing.finish_folders(self._handle, items, addon.ADDON_NAME)

    def _list_subscriptions(self):
        """Show the subscribed channels."""
        channels = self._query_data_api(dataapi.subscriptions)
        if channels is None:
            return

        items = [listing.folder_item(channel.title, 'channel', channel.thumbnail,
                                     id=channel.channel_id, title=channel.title)
                 for channel in channels]
        listing.finish_folders(self._handle, items, addon.localize(30200))

    def _list_channel(self):
        """Show the newest videos of a channel. Parameters: id, title."""
        videos = self._query_data_api(dataapi.channel_videos, self._params.get('id', ''),
                                      CHANNEL_VIDEO_COUNT)
        if videos is None:
            return

        listing.finish_videos(self._handle, [listing.video_item(video) for video in videos],
                              listing.breadcrumb(addon.localize(30200),
                                                 self._params.get('title', '')))

    def _query_data_api(self, query, *args):
        """Run a query on behalf of the signed-in account.

        Returns None if that fails, after telling the user and Kodi.
        """
        token = account.access_token(account.USER)
        if token is None:
            return self._fail(addon.localize(30105))

        try:
            return query(*args, token=token)
        except dataapi.DataApiError as error:
            addon.log_error('YouTube Data API: {}'.format(error))
            return self._fail(addon.localize(30104 if str(error) == 'quotaExceeded' else 30103))
        except http.RequestError as error:
            addon.log_error(str(error))
            return self._fail(addon.localize(30101))

    def _fail(self, message):
        addon.notify(message)
        xbmcplugin.endOfDirectory(self._handle, succeeded=False)

    def _play(self):
        """Play the video given by its id. Parameter: v."""
        playback.play(self._handle, self._params.get('v', ''))

    def _sign_in(self):
        """Sign in to YouTube, run from the settings."""
        account.sign_in()

    def _sign_out(self):
        """Sign out of YouTube, run from the settings."""
        account.sign_out()


_ROUTES = {
    '': Router._list_root,
    'subscriptions': Router._list_subscriptions,
    'channel': Router._list_channel,
    'play': Router._play,
    'signin': Router._sign_in,
    'signout': Router._sign_out,
}
