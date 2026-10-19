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

import json
import os
import shutil
import sys
import tempfile
import time
import types
import unittest

LOG = []
NOTIFICATIONS = []
BUILTINS = []
CONFIRMATIONS = []
CONFIRM_ANSWER = [True]
INPUT_ANSWER = ['']
PLUGIN_ITEMS = []
PLUGIN_STATE = {}
INFO_LABELS = {}
#: The conditions getCondVisibility() finds true, besides a paused playback.
CONDITIONS = set()
LANGUAGE = ['de']
ABORT_REQUESTED = [False]
DEFAULT_SETTINGS = {
    'api_key': '',
    'client_id': '',
    'client_secret': '',
    'signed_in': False,
    'video_codecs': ['vp9', 'avc1'],
    'offer_auto_dubs': True,
    'sync_playback': False,
}
SETTINGS = dict(DEFAULT_SETTINGS)
#: Progress dialogue events, and whether the user pressed cancel.
PROGRESS = []
PROGRESS_CANCELED = [False]
#: What Kodi plays, second by second: (file, position, paused), or None for
#: nothing. Every waitForAbort() moves on to the next second; after the last
#: one, Kodi plays nothing.
PLAYBACK = []

PROFILE_DIR = os.path.join(tempfile.gettempdir(), 'plugin.video.yt-test-profile')


def _make_module(name):
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


# -- xbmc ---------------------------------------------------------------------

xbmc = _make_module('xbmc')
xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = 0, 1, 2, 3
xbmc.log = lambda message, level=0: LOG.append((level, message))
xbmc.executebuiltin = lambda command: BUILTINS.append(command)
xbmc.ISO_639_1 = 0
xbmc.getLanguage = lambda format=0, region=False: LANGUAGE[0]
xbmc.getInfoLabel = lambda label: INFO_LABELS.get(label, '')
xbmc.getRegion = lambda name: {'dateshort': '%d.%m.%Y', 'time': '%H:%M:%S'}[name]


class Monitor:
    def abortRequested(self):
        return ABORT_REQUESTED[0]

    def waitForAbort(self, timeout=None):
        if PLAYBACK:
            PLAYBACK.pop(0)
        return ABORT_REQUESTED[0]


def _playing():
    if not PLAYBACK or PLAYBACK[0] is None:
        raise RuntimeError('Kodi is not playing any file')
    return PLAYBACK[0]


class Player:
    def getPlayingFile(self):
        return _playing()[0]

    def getTime(self):
        return _playing()[1]


xbmc.Monitor = Monitor
xbmc.Player = Player
xbmc.getCondVisibility = lambda condition: (condition in CONDITIONS
                                            or condition == 'Player.Paused'
                                            and bool(PLAYBACK) and PLAYBACK[0] is not None
                                            and PLAYBACK[0][2])

# -- xbmcaddon ----------------------------------------------------------------

xbmcaddon = _make_module('xbmcaddon')

ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings:
    def getString(self, setting_id):
        return SETTINGS[setting_id]

    def getStringList(self, setting_id):
        return SETTINGS[setting_id]

    def getBool(self, setting_id):
        return SETTINGS[setting_id]

    def setBool(self, setting_id, value):
        SETTINGS[setting_id] = value


class Addon:
    _INFO = {'id': 'plugin.video.yt',
             'name': 'YouTube',
             'icon': 'icon.png',
             'path': ADDON_DIR,
             'profile': 'special://profile/addon_data/plugin.video.yt/'}

    def getAddonInfo(self, key):
        return self._INFO[key]

    def getLocalizedString(self, string_id):
        return 'L{}'.format(string_id)

    def getSettings(self):
        return Settings()


xbmcaddon.Addon = Addon

# -- xbmcvfs ------------------------------------------------------------------

xbmcvfs = _make_module('xbmcvfs')
xbmcvfs.translatePath = lambda path: PROFILE_DIR

# -- xbmcgui ------------------------------------------------------------------

xbmcgui = _make_module('xbmcgui')


class InfoTagVideo:
    """Records every setter call as values[<name without 'set'>]."""

    def __init__(self):
        self.values = {}

    def __getattr__(self, name):
        if not name.startswith('set'):
            raise AttributeError(name)

        def setter(*args):
            self.values[name[3:]] = args[0] if len(args) == 1 else args
        return setter


class ListItem:
    def __init__(self, label='', label2='', path='', offscreen=False):
        self.label = label
        self.path = path
        self.mime_type = None
        self.content_lookup = True
        self.properties = {}
        self.is_folder = None
        self.art = {}
        self.date_time = None
        self.info_tag = InfoTagVideo()
        self.context_menu = []

    def addContextMenuItems(self, items, replaceItems=False):
        self.context_menu.extend(items)

    def setIsFolder(self, is_folder):
        self.is_folder = is_folder

    def setArt(self, art):
        self.art.update(art)

    def setDateTime(self, date_time):
        self.date_time = date_time

    def getVideoInfoTag(self):
        return self.info_tag

    def setMimeType(self, mime_type):
        self.mime_type = mime_type

    def setContentLookup(self, enable):
        self.content_lookup = enable

    def setProperty(self, key, value):
        self.properties[key] = value


class Dialog:
    def notification(self, heading, message, icon=None, time=5000, sound=True):
        NOTIFICATIONS.append((heading, message))

    def yesno(self, heading, message, *args, **kwargs):
        CONFIRMATIONS.append((heading, message))
        return CONFIRM_ANSWER[0]

    def input(self, heading, defaultt='', type=0, option=0, autoclose=0):
        return INPUT_ANSWER[0]


class DialogProgress:
    def create(self, heading, message=''):
        PROGRESS.append(('create', heading, message))

    def update(self, percent, message=''):
        PROGRESS.append(('update', percent, message))

    def iscanceled(self):
        return PROGRESS_CANCELED[0]

    def close(self):
        PROGRESS.append(('close',))


xbmcgui.ListItem = ListItem
xbmcgui.Dialog = Dialog
xbmcgui.DialogProgress = DialogProgress

# -- xbmcplugin ---------------------------------------------------------------

xbmcplugin = _make_module('xbmcplugin')


def _add_directory_items(handle, items, total=0):
    PLUGIN_ITEMS.extend(items)
    return True


def _end_of_directory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    PLUGIN_STATE['succeeded'] = succeeded
    PLUGIN_STATE['cacheToDisc'] = cacheToDisc


def _set_resolved_url(handle, succeeded, listitem):
    PLUGIN_STATE['resolved'] = succeeded
    PLUGIN_STATE['resolved_item'] = listitem


xbmcplugin.SORT_METHOD_UNSORTED = 'unsorted'
xbmcplugin.SORT_METHOD_LABEL = 'label'
xbmcplugin.SORT_METHOD_DATE = 'date'
xbmcplugin.SORT_METHOD_TITLE = 'title'
xbmcplugin.SORT_METHOD_DURATION = 'duration'
xbmcplugin.addDirectoryItems = _add_directory_items
xbmcplugin.endOfDirectory = _end_of_directory
xbmcplugin.setResolvedUrl = _set_resolved_url
xbmcplugin.setPluginCategory = lambda handle, category: PLUGIN_STATE.__setitem__('category',
                                                                                category)
xbmcplugin.setContent = lambda handle, content: PLUGIN_STATE.__setitem__('content', content)
def _add_sort_method(handle, sortMethod, labelMask='', label2Mask=''):
    PLUGIN_STATE.setdefault('sort_methods', []).append(sortMethod)
    PLUGIN_STATE.setdefault('label2_masks', {})[sortMethod] = label2Mask


xbmcplugin.addSortMethod = _add_sort_method


def reset_output():
    del LOG[:], NOTIFICATIONS[:], PLUGIN_ITEMS[:], BUILTINS[:], CONFIRMATIONS[:]
    PLUGIN_STATE.clear()


def reset():
    reset_output()
    INFO_LABELS.clear()
    CONDITIONS.clear()
    LANGUAGE[0] = 'de'
    ABORT_REQUESTED[0] = False
    CONFIRM_ANSWER[0] = True
    INPUT_ANSWER[0] = ''
    SETTINGS.clear()
    SETTINGS.update(DEFAULT_SETTINGS)
    del PROGRESS[:]
    PROGRESS_CANCELED[0] = False
    del PLAYBACK[:]
    shutil.rmtree(PROFILE_DIR, ignore_errors=True)


def tokens(name, expires_in=3600):
    """Tokens as account.py keeps them for one account."""
    return {'access_token': 'access-' + name, 'refresh_token': 'refresh-' + name,
            'expires_at': time.time() + expires_in}


def store_tokens(**all_tokens):
    """Sign in by putting the tokens file in place."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    with open(os.path.join(PROFILE_DIR, 'tokens.json'), 'w', encoding='utf-8') as tokens_file:
        json.dump(all_tokens, tokens_file)
    SETTINGS['signed_in'] = True


# -- YouTube data -------------------------------------------------------------

def video_format(itag, mime_type, height, bitrate, **extra):
    """An entry of streamingData.adaptiveFormats for a video stream."""
    data = {
        'itag': itag,
        'url': 'https://rr1.googlevideo.com/videoplayback?itag={}&mime=video&ip=1'.format(itag),
        'mimeType': mime_type,
        'bitrate': bitrate,
        'width': height * 16 // 9,
        'height': height,
        'initRange': {'start': '0', 'end': '219'},
        'indexRange': {'start': '220', 'end': '1000'},
        'approxDurationMs': '212091',
    }
    data.update(extra)
    return data


def audio_format(itag, mime_type, bitrate, **extra):
    """An entry of streamingData.adaptiveFormats for an audio stream."""
    data = {
        'itag': itag,
        'url': 'https://rr1.googlevideo.com/videoplayback?itag={}&mime=audio&ip=1'.format(itag),
        'mimeType': mime_type,
        'bitrate': bitrate,
        'initRange': {'start': '0', 'end': '265'},
        'indexRange': {'start': '266', 'end': '600'},
        'approxDurationMs': '212141',
        'audioSampleRate': '48000',
        'audioChannels': 2,
    }
    data.update(extra)
    return data


VP9_1080 = video_format(248, 'video/webm; codecs="vp9"', 1080, 2500000)
VP9_720 = video_format(247, 'video/webm; codecs="vp9"', 720, 1400000)
AVC_1080 = video_format(137, 'video/mp4; codecs="avc1.640028"', 1080, 4400000)
AV1_1080 = video_format(399, 'video/mp4; codecs="av01.0.08M.08"', 1080, 2100000)
VP9_HDR_1080 = video_format(
    337, 'video/webm; codecs="vp09.02.51.10.01.09.16.09.00"', 1080, 3800000,
    colorInfo={'primaries': 'COLOR_PRIMARIES_BT2020',
               'transferCharacteristics': 'COLOR_TRANSFER_CHARACTERISTICS_SMPTEST2084',
               'matrixCoefficients': 'COLOR_MATRIX_COEFFICIENTS_BT2020_NCL'})
OPUS = audio_format(251, 'audio/webm; codecs="opus"', 140000)
AAC = audio_format(140, 'audio/mp4; codecs="mp4a.40.2"', 130000)


def tagged_audio_format(itag, track_id, content, is_default=False):
    """An Opus format of one of several audio tracks, tagged as YouTube does, e.g. 'original'."""
    data = audio_format(itag, 'audio/webm; codecs="opus"', 140000,
                        audioTrack={'id': track_id, 'audioIsDefault': is_default})
    data['url'] += '&xtags=acont%3D{}%3Alang%3D{}'.format(content, track_id.partition('.')[0])
    return data


ORIGINAL_EN = tagged_audio_format(251, 'en-US.4', 'original')
#: The track YouTube picks for German, dubbed automatically.
AUTO_DUB_DE = tagged_audio_format(1251, 'de-DE.10', 'dubbed-auto', is_default=True)


def player_response(video_id, formats=(VP9_1080, AVC_1080, OPUS, AAC), **details):
    """A player response with the given adaptive formats."""
    video_details = {'videoId': video_id, 'title': 'Some video', 'lengthSeconds': '212'}
    video_details.update(details)
    return {
        'playabilityStatus': {'status': 'OK'},
        'videoDetails': video_details,
        'streamingData': {'expiresInSeconds': '21540', 'adaptiveFormats': list(formats)},
    }


# The add-on modules must not be imported before the stubs above are in place.
sys.path.insert(0, ADDON_DIR)

from resources.lib.router import Router  # noqa: E402

BASE_URL = 'plugin://plugin.video.yt/'


class AddonTestCase(unittest.TestCase):
    """Gives every test clean stubs and an empty profile."""

    def setUp(self):
        reset()

    def tearDown(self):
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)

    def dispatch(self, route='', query=''):
        """Run the plugin for the given route and query and return its items."""
        reset_output()
        Router([BASE_URL + route, '1', query]).dispatch()
        return list(PLUGIN_ITEMS)

    @staticmethod
    def errors():
        return [message for level, message in LOG if level == xbmc.LOGERROR]

    @staticmethod
    def warnings():
        return [message for level, message in LOG if level == xbmc.LOGWARNING]
