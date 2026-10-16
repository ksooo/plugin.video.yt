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

import xbmc
import xbmcplugin

from . import account
from . import addon
from . import dataapi
from . import http
from . import listing
from . import playback
from . import subscriptions

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
        channels = self._query_data_api(subscriptions.list_channels)
        if channels is None:
            return

        # Going back to it after unsubscribing must not show the channel.
        listing.finish_folders(self._handle, [listing.channel_item(channel)
                                              for channel in channels],
                               addon.localize(30200), cache=False)

    def _list_channel(self):
        """Show the newest videos of a channel. Parameters: id, title."""
        channel_id = self._params.get('id', '')
        result = self._query_data_api(lambda token: (
            dataapi.channel_videos(channel_id, CHANNEL_VIDEO_COUNT, token=token),
            channel_id in subscriptions.subscription_ids(token)))
        if result is None:
            return

        videos, subscribed = result
        listing.finish_videos(self._handle,
                              [listing.video_item(video, subscribed, link_channel=False)
                               for video in videos],
                              listing.breadcrumb(addon.localize(30200),
                                                 self._params.get('title', '')))

    def _unsubscribe(self):
        """Unsubscribe from a channel, run from a context menu. Parameters: channel, title."""
        if not addon.confirm(addon.localize(30212).format(self._params.get('title', ''))):
            return
        if not self._change_subscription(subscriptions.unsubscribe, 30211):
            return

        # Leave the listing of the channel just unsubscribed from, it belongs
        # to the subscriptions no more.
        folder = urlsplit(xbmc.getInfoLabel('Container.FolderPath'))
        if (folder.path.strip('/') == 'channel'
                and dict(parse_qsl(folder.query)).get('id') == self._params.get('channel')):
            xbmc.executebuiltin('Action(ParentDir)')
        else:
            xbmc.executebuiltin('Container.Refresh')

    def _subscribe(self):
        """Subscribe to a channel, run from a context menu. Parameters: channel, title."""
        if self._change_subscription(subscriptions.subscribe, 30210):
            # The context menus of the listing have to follow.
            xbmc.executebuiltin('Container.Refresh')

    def _change_subscription(self, change, done_label_id):
        """Apply the change and report it. Returns whether it succeeded."""
        channel_id = self._params.get('channel', '')

        def changed(token):
            change(channel_id, token=token)
            return True

        if not self._query_data_api(changed, listing_route=False):
            return False

        addon.notify(addon.localize(done_label_id).format(self._params.get('title', '')))
        return True

    def _query_data_api(self, query, listing_route=True):
        """Run query(token) on behalf of the signed-in account and return its result.

        Returns None if that fails, after telling the user and, for a listing,
        Kodi.
        """
        token = account.access_token(account.USER)
        if token is None:
            return self._fail(addon.localize(30105), listing_route)

        try:
            return query(token)
        except dataapi.DataApiError as error:
            addon.log_error('YouTube Data API: {}'.format(error))
            return self._fail(addon.localize(30104 if str(error) == 'quotaExceeded' else 30103),
                              listing_route)
        except http.RequestError as error:
            addon.log_error(str(error))
            return self._fail(addon.localize(30101), listing_route)

    def _fail(self, message, listing_route):
        addon.notify(message)
        if listing_route:
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
    'subscribe': Router._subscribe,
    'unsubscribe': Router._unsubscribe,
    'play': Router._play,
    'signin': Router._sign_in,
    'signout': Router._sign_out,
}
