# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Thin convenience layer around the Kodi add-on API."""

import json
import os
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_ICON = ADDON.getAddonInfo('icon')

# Setting identifiers, must match resources/settings.xml.
SETTING_API_KEY = 'api_key'
SETTING_CLIENT_ID = 'client_id'
SETTING_CLIENT_SECRET = 'client_secret'
SETTING_SIGNED_IN = 'signed_in'
SETTING_VIDEO_CODECS = 'video_codecs'
SETTING_SKIP_AUTO_DUBS = 'skip_auto_dubs'
SETTING_SYNC_PLAYBACK = 'sync_playback'


def localize(string_id):
    """Return the localised string with the given identifier."""
    return ADDON.getLocalizedString(string_id)


def language():
    """Return Kodi's language as ISO 639-1 code such as 'de'."""
    return xbmc.getLanguage(xbmc.ISO_639_1)


def region():
    """Return Kodi's region as ISO 3166 code such as 'DE', empty if unknown."""
    return xbmc.getInfoLabel('System.Locale(iso)')


def local_date_time(timestamp):
    """Return the date and the time of a moment as Kodi's region shows them, without seconds."""
    moment = time.localtime(timestamp)
    return (time.strftime(xbmc.getRegion('dateshort'), moment),
            time.strftime(xbmc.getRegion('time').replace(':%S', ''), moment))


def ask_text(heading):
    """Let the user type a text. Returns it stripped, empty if cancelled."""
    return xbmcgui.Dialog().input(heading).strip()


def get_string_setting(setting_id):
    """Return the value of a text setting, stripped of stray whitespace."""
    return ADDON.getSettings().getString(setting_id).strip()


def get_bool_setting(setting_id):
    """Return whether a boolean setting is on."""
    return ADDON.getSettings().getBool(setting_id)


def get_string_list_setting(setting_id):
    """Return the values chosen in a multi-select setting."""
    return ADDON.getSettings().getStringList(setting_id)


def set_bool_setting(setting_id, value):
    """Change a boolean setting."""
    ADDON.getSettings().setBool(setting_id, value)


def profile_path(file_name):
    """Return the full path of a file in the add-on's profile directory, creating that."""
    return _path_in(ADDON.getAddonInfo('profile'), file_name)


def temp_path(file_name):
    """Return the full path of a file in the add-on's part of Kodi's temp directory."""
    return _path_in('special://temp/{}/'.format(ADDON_ID), file_name)


def _path_in(directory, file_name):
    directory = xbmcvfs.translatePath(directory)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, file_name)


def load_json(path, default):
    """Return the data kept in the JSON file, or default if there is none."""
    try:
        with open(path, encoding='utf-8') as json_file:
            return json.load(json_file)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file)


def cached(file_name, key, max_age_seconds, fetch):
    """Return what fetch() returned for the key, kept in a file of Kodi's temp directory.

    Entries older than max_age_seconds are fetched anew. Kept as JSON, tuples
    come back as lists.
    """
    path = temp_path(file_name)
    now = time.time()
    cache = {cached_key: entry for cached_key, entry in load_json(path, {}).items()
             if now - entry['saved_at'] < max_age_seconds}
    if key not in cache:
        cache[key] = {'saved_at': now, 'data': fetch()}
        save_json(path, cache)
    return cache[key]['data']


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
