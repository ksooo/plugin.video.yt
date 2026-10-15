# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""A simulated Kodi for the tests: xbmc* stubs and a base case.

Importing this module installs the stubs, so it has to come before any import
of resources.lib.
"""

import os
import sys
import types
import unittest

LOG = []
NOTIFICATIONS = []
PLUGIN_ITEMS = []
PLUGIN_STATE = {}


def _make_module(name):
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


# -- xbmc ---------------------------------------------------------------------

xbmc = _make_module('xbmc')
xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 3
xbmc.log = lambda message, level=0: LOG.append((level, message))

# -- xbmcaddon ----------------------------------------------------------------

xbmcaddon = _make_module('xbmcaddon')

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Addon:
    _INFO = {'id': 'plugin.video.yt',
             'name': 'YouTube',
             'icon': 'icon.png',
             'path': ADDON_DIR}

    def getAddonInfo(self, key):
        return self._INFO[key]

    def getLocalizedString(self, string_id):
        return 'L{}'.format(string_id)


xbmcaddon.Addon = Addon

# -- xbmcgui ------------------------------------------------------------------

xbmcgui = _make_module('xbmcgui')


class Dialog:
    def notification(self, heading, message, icon=None, time=5000, sound=True):
        NOTIFICATIONS.append((heading, message))


xbmcgui.Dialog = Dialog

# -- xbmcplugin ---------------------------------------------------------------

xbmcplugin = _make_module('xbmcplugin')


def _add_directory_items(handle, items, total=0):
    PLUGIN_ITEMS.extend(items)
    return True


def _end_of_directory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    PLUGIN_STATE['succeeded'] = succeeded
    PLUGIN_STATE['cacheToDisc'] = cacheToDisc


xbmcplugin.addDirectoryItems = _add_directory_items
xbmcplugin.endOfDirectory = _end_of_directory


def reset():
    del LOG[:], NOTIFICATIONS[:], PLUGIN_ITEMS[:]
    PLUGIN_STATE.clear()


# The add-on modules must not be imported before the stubs above are in place.
sys.path.insert(0, ADDON_DIR)

from resources.lib.router import Router  # noqa: E402

BASE_URL = 'plugin://plugin.video.yt/'


class AddonTestCase(unittest.TestCase):
    """Gives every test clean stubs."""

    def setUp(self):
        reset()

    def dispatch(self, route='', query=''):
        """Run the plugin for the given route and query and return its items."""
        reset()
        Router([BASE_URL + route, '1', query]).dispatch()
        return list(PLUGIN_ITEMS)

    @staticmethod
    def errors():
        return [message for level, message in LOG if level == xbmc.LOGERROR]
