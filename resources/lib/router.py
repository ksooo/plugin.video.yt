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
from . import search
from . import subscriptions

#: The most videos listed for a channel or as trending.
VIDEO_COUNT = 100

#: The most videos listed for a search; a page of 50 costs 101 quota units.
SEARCH_COUNT = 50



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

    # -- listings -----------------------------------------------------------

    def _list_root(self):
        """Show the top level of the add-on."""
        items = []
        signed_in = account.is_signed_in()
        if signed_in:
            items.append(listing.folder_item(addon.localize(30200), 'subscriptions'))
        if signed_in or addon.get_string_setting(addon.SETTING_API_KEY):
            items.append(listing.folder_item(addon.localize(30300), 'trending'))
            items.append(listing.folder_item(addon.localize(30301), 'search'))
        listing.finish_folders(self._handle, items, addon.ADDON_NAME)

    def _list_subscriptions(self):
        """Show the subscribed channels."""
        channels = self._query_data_api(subscriptions.list_channels, need_account=True)
        if channels is None:
            return

        # Going back to it after unsubscribing must not show the channel.
        listing.finish_folders(self._handle, [listing.channel_item(channel)
                                              for channel in channels],
                               addon.localize(30200), cache=False)

    def _list_channel(self):
        """Show the newest videos of a channel. Parameters: id, title, parent."""
        channel_id = self._params.get('id', '')
        title = self._params.get('title', '')

        def query(auth):
            subscribed = None
            if auth.token:
                subscribed = channel_id in subscriptions.subscription_ids(auth)
            return dataapi.channel_videos(channel_id, VIDEO_COUNT, auth=auth), subscribed

        result = self._query_data_api(query)
        if result is None:
            return

        videos, subscribed = result
        category = title
        if self._params.get('parent') == 'subscriptions':
            category = listing.breadcrumb(addon.localize(30200), title)
        listing.finish_videos(self._handle,
                              [listing.video_item(video, subscribed, link_channel=False)
                               for video in videos],
                              category)

    def _list_trending(self):
        """Show the most popular videos in Kodi's region."""
        self._list_videos(lambda auth: dataapi.most_popular(addon.region(), VIDEO_COUNT,
                                                            auth=auth),
                          addon.localize(30300))

    def _list_search(self):
        """Show the entries to search anew and to search again."""
        listing.finish_folders(self._handle,
                               [listing.action_item(addon.localize(30303), 'search/new',
                                                    'DefaultAddonsSearch.png'),
                                listing.folder_item(addon.localize(30302), 'search/recent')],
                               addon.localize(30301))

    def _new_search(self):
        """Ask for what to search and show the results, run as an action."""
        query = addon.ask_text(addon.localize(30301))
        if query:
            # The results have a URL of their own, so that going back to them
            # does not ask again.
            xbmc.executebuiltin('Container.Update({})'.format(listing.url('search/results',
                                                                          q=query)))

    def _list_recent_searches(self):
        """Show the recent searches, the newest first."""
        listing.finish_folders(self._handle,
                               [listing.search_item(query) for query in search.recent()],
                               listing.breadcrumb(addon.localize(30301),
                                                  addon.localize(30302)),
                               cache=False)

    def _list_search_results(self):
        """Show the videos found for a query. Parameter: q."""
        query = self._params.get('q', '')
        search.remember(query)
        self._list_videos(lambda auth: search.results(query, addon.region(), addon.language(),
                                                      SEARCH_COUNT, auth),
                          listing.breadcrumb(addon.localize(30301), query),
                          nothing_found_label_id=30107)

    def _list_videos(self, query, category, nothing_found_label_id=None):
        """Show the videos of various channels query(auth) returns.

        With nothing_found_label_id, finding no video is reported with that
        message and Kodi stays where it is.
        """
        def videos_and_subscriptions(auth):
            ids = subscriptions.subscription_ids(auth) if auth.token else None
            return query(auth), ids

        result = self._query_data_api(videos_and_subscriptions)
        if result is None:
            return

        videos, ids = result
        if not videos and nothing_found_label_id is not None:
            self._fail(addon.localize(nothing_found_label_id), listing_route=True)
            return

        listing.finish_videos(self._handle,
                              [listing.video_item(video,
                                                  None if ids is None else video.channel_id in ids,
                                                  link_channel=True)
                               for video in videos],
                              category)

    # -- actions ------------------------------------------------------------

    def _forget_search(self):
        """Delete a recent search, run from a context menu. Parameter: q."""
        if addon.confirm(addon.localize(30305)):
            search.forget(self._params.get('q', ''))
            xbmc.executebuiltin('Container.Refresh')

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

        def changed(auth):
            change(channel_id, auth=auth)
            return True

        if not self._query_data_api(changed, need_account=True, listing_route=False):
            return False

        addon.notify(addon.localize(done_label_id).format(self._params.get('title', '')))
        return True

    def _play(self):
        """Play the video given by its id. Parameter: v."""
        playback.play(self._handle, self._params.get('v', ''))

    def _sign_in(self):
        """Sign in to YouTube, run from the settings."""
        account.sign_in()

    def _sign_out(self):
        """Sign out of YouTube, run from the settings."""
        account.sign_out()

    # -- data API -----------------------------------------------------------

    def _query_data_api(self, query, need_account=False, listing_route=True):
        """Run query(auth) and return its result.

        The query runs on behalf of the signed-in account, else - unless it
        needs the account - with the API key. Returns None if that fails,
        after telling the user and, for a listing, Kodi.
        """
        token = account.access_token(account.USER) if account.is_signed_in() else None
        api_key = addon.get_string_setting(addon.SETTING_API_KEY)
        if token is None and (need_account or not api_key):
            return self._fail(addon.localize(30105 if need_account else 30106), listing_route)

        try:
            return query(dataapi.Auth(token, api_key))
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


_ROUTES = {
    '': Router._list_root,
    'subscriptions': Router._list_subscriptions,
    'channel': Router._list_channel,
    'trending': Router._list_trending,
    'search': Router._list_search,
    'search/new': Router._new_search,
    'search/recent': Router._list_recent_searches,
    'search/results': Router._list_search_results,
    'search/forget': Router._forget_search,
    'subscribe': Router._subscribe,
    'unsubscribe': Router._unsubscribe,
    'play': Router._play,
    'signin': Router._sign_in,
    'signout': Router._sign_out,
}
