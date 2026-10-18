# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Resolving a video to streams Kodi can play."""

from urllib.parse import urlencode

import xbmc
import xbmcgui
import xbmcplugin

from . import account
from . import addon
from . import feeds
from . import http
from . import innertube
from . import manifest
from . import watchtime
from .manifestserver import ManifestServer

#: ISA fetches the manifest right after the URL is resolved.
MANIFEST_TIMEOUT_SECONDS = 30


def play(handle, video_id):
    """Resolve the plugin URL of the video for Kodi's player."""
    try:
        player = innertube.get_player(video_id, addon.language(), addon.region(),
                                      account.access_token)
    except innertube.PlayabilityError as error:
        addon.log('{} not playable: {}'.format(video_id, error))
        if error.starts_at:
            # YouTube words the start wrongly in some languages, "in 4 Tage" in German.
            _fail(handle, addon.localize(30108).format(*addon.local_date_time(error.starts_at)))
        elif error.sign_in_would_help:
            _fail(handle, addon.localize(30102))
        else:
            _fail(handle, str(error) or addon.localize(30100))
        return
    except http.RequestError as error:
        addon.log_error(str(error))
        _fail(handle, addon.localize(30101))
        return

    addon.log('{} served to {}'.format(video_id, player.client.name))
    headers = urlencode(player.client.stream_headers)
    streaming_data = player.response.get('streamingData', {})
    if player.response['videoDetails'].get('isLive'):
        _play_live(handle, streaming_data.get('hlsManifestUrl'), headers)
    else:
        captions = player.response.get('captions', {}).get(
            'playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
        url = _play_video(handle, video_id, streaming_data.get('adaptiveFormats', []),
                          captions, headers)
        if url is not None:
            _sync(player, video_id, url)


def _play_live(handle, hls_url, headers):
    if not hls_url:
        _fail(handle, addon.localize(30100))
        return

    list_item = _make_list_item(hls_url, 'application/vnd.apple.mpegurl', headers)
    list_item.setProperty('inputstream.adaptive.manifest_headers', headers)
    xbmcplugin.setResolvedUrl(handle, True, list_item)


def _play_video(handle, video_id, formats, captions, headers):
    """Hand the video to Kodi. Returns the URL Kodi plays it from, None if that failed."""
    mpd = manifest.build(formats, captions,
                         addon.get_string_list_setting(addon.SETTING_VIDEO_CODECS),
                         prefer_hdr=bool(xbmc.getInfoLabel('System.SupportedHDRTypes')))
    if mpd is None:
        addon.log('{} has no usable formats'.format(video_id))
        _fail(handle, addon.localize(30100))
        return None

    server = ManifestServer(mpd)
    xbmcplugin.setResolvedUrl(handle, True,
                              _make_list_item(server.url, 'application/dash+xml', headers))
    if not server.serve(MANIFEST_TIMEOUT_SECONDS, xbmc.Monitor().abortRequested):
        addon.log_error('manifest of {} was never fetched'.format(video_id))
        return None
    return server.url


def _sync(player, video_id, url):
    """Report the playback to the account's watch history while it lasts, if syncing."""
    token = account.sync_token()
    if token is None:
        return

    if player.client is innertube.ANDROID_VR:
        # Asked signed in, so the URLs are the account's already.
        tracking = player.response.get('playbackTracking')
    else:
        try:
            response = innertube.get_signed_in_player(video_id, addon.language(),
                                                      addon.region(), token)
        except http.RequestError as error:
            addon.log_error(str(error))
            return
        tracking = response.get('playbackTracking') if response else None
    if not tracking:
        addon.log('{} cannot be reported to the watch history'.format(video_id))
        return

    position = watchtime.follow(url, tracking)
    length = int(player.response['videoDetails'].get('lengthSeconds', 0))
    if position is not None and length:
        feeds.watched(video_id, min(100, round(position * 100 / length)))


def _make_list_item(url, mime_type, headers):
    list_item = xbmcgui.ListItem(path=url, offscreen=True)
    list_item.setMimeType(mime_type)
    list_item.setContentLookup(False)
    list_item.setProperty('inputstream', 'inputstream.adaptive')
    list_item.setProperty('inputstream.adaptive.stream_headers', headers)
    return list_item


def _fail(handle, message):
    addon.notify(message)
    xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem(offscreen=True))
