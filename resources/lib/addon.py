# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Thin convenience layer around the Kodi add-on API."""

import os

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_ICON = ADDON.getAddonInfo('icon')

# Setting identifiers, must match resources/settings.xml.
SETTING_CLIENT_ID = 'client_id'
SETTING_CLIENT_SECRET = 'client_secret'
SETTING_SIGNED_IN = 'signed_in'


def localize(string_id):
    """Return the localised string with the given identifier."""
    return ADDON.getLocalizedString(string_id)


def get_string_setting(setting_id):
    """Return the value of a text setting, stripped of stray whitespace."""
    return ADDON.getSettings().getString(setting_id).strip()


def set_bool_setting(setting_id, value):
    """Change a boolean setting."""
    ADDON.getSettings().setBool(setting_id, value)


def profile_path(file_name):
    """Return the full path of a file in the add-on's profile directory, creating that."""
    directory = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, file_name)


def log(message, level=xbmc.LOGDEBUG):
    """Write a message prefixed with the add-on id to the Kodi log."""
    xbmc.log('[{}] {}'.format(ADDON_ID, message), level)


def log_error(message):
    """Write an error message to the Kodi log."""
    log(message, xbmc.LOGERROR)


def notify(message, heading=None, time=5000):
    """Show a notification toast."""
    xbmcgui.Dialog().notification(heading or ADDON_NAME, message, ADDON_ICON, time)


def confirm(message):
    """Ask a yes/no question and return whether the answer was yes."""
    return xbmcgui.Dialog().yesno(ADDON_NAME, message)
