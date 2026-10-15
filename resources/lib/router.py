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
e.g. plugin://plugin.video.yt/play?v=<id>. Kodi stores resume points and play
counts under these URLs, so the URL of a video must never change.
"""

from urllib.parse import parse_qsl
from urllib.parse import urlsplit

import xbmcplugin

from . import addon
from . import playback


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
        xbmcplugin.endOfDirectory(self._handle)

    def _play(self):
        """Play the video given by its id. Parameter: v."""
        playback.play(self._handle, self._params.get('v', ''))


_ROUTES = {
    '': Router._list_root,
    'play': Router._play,
}
